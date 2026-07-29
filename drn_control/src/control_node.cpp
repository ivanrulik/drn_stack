// Copyright 2026 Ivan Rulik
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
// THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

#include <Eigen/Core>
#include <cmath>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>

#include <drn_control/pose_conversion.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_command_ack.hpp>
#include <px4_msgs/srv/vehicle_command.hpp>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/mode_executor.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/multicopter/goto.hpp>
#include <px4_ros2/odometry/local_position.hpp>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_srvs/srv/trigger.hpp>

namespace drn_control
{

namespace
{

constexpr char kModeName[] = "DRN Control";
constexpr char kStatusTopic[] = "/drn/control/status";
constexpr char kSetpointTopic[] = "/drn/control/setpoint";

float positiveParameter(rclcpp::Node & node, const std::string & name, double default_value)
{
  const double value = node.declare_parameter<double>(name, default_value);
  if (!std::isfinite(value) || value <= 0.0) {
    throw std::invalid_argument(name + " must be finite and positive");
  }
  return static_cast<float>(value);
}

}  // namespace

class DrnControlMode : public px4_ros2::ModeBase
{
public:
  explicit DrnControlMode(rclcpp::Node & node)
  : ModeBase(node, Settings{kModeName}),
    command_frame_(node.declare_parameter<std::string>("command_frame", "map")),
    max_abs_position_m_(
      positiveParameter(node, "max_abs_position_m", 1000.0)),
    max_horizontal_speed_m_s_(
      positiveParameter(node, "max_horizontal_speed_m_s", 2.0)),
    max_vertical_speed_m_s_(
      positiveParameter(node, "max_vertical_speed_m_s", 1.0)),
    max_heading_rate_rad_s_(
      positiveParameter(node, "max_heading_rate_rad_s", 0.8))
  {
    if (command_frame_.empty()) {
      throw std::invalid_argument("command_frame must not be empty");
    }

    goto_setpoint_ = std::make_shared<px4_ros2::MulticopterGotoSetpointType>(*this);
    local_position_ = std::make_shared<px4_ros2::OdometryLocalPosition>(*this);

    status_publisher_ = node.create_publisher<std_msgs::msg::String>(
      kStatusTopic,
      rclcpp::QoS(1).reliable().transient_local());
    setpoint_subscription_ = node.create_subscription<geometry_msgs::msg::PoseStamped>(
      kSetpointTopic,
      rclcpp::QoS(1).reliable(),
      [this](geometry_msgs::msg::PoseStamped::ConstSharedPtr message) {
        receiveSetpoint(*message);
      });

    publishStatus("waiting_for_px4");
  }

  void onActivate() override
  {
    if (captureCurrentTarget()) {
      publishStatus("holding");
    } else {
      publishStatus("error: local position unavailable");
    }
  }

  void onDeactivate() override
  {
    target_.reset();
  }

  void updateSetpoint(float) override
  {
    if (!target_.has_value()) {
      return;
    }

    goto_setpoint_->update(
      target_->position_m,
      target_->heading_rad,
      max_horizontal_speed_m_s_,
      max_vertical_speed_m_s_,
      max_heading_rate_rad_s_);
  }

  bool captureCurrentTarget()
  {
    if (!local_position_->positionXYValid() || !local_position_->positionZValid()) {
      return false;
    }

    const Eigen::Vector3f position = local_position_->positionNed();
    if (!position.allFinite()) {
      return false;
    }

    const float heading = local_position_->heading();
    target_ = NedSetpoint{
      position,
      std::isfinite(heading) ? std::optional<float>{heading} : std::nullopt};
    return true;
  }

  void publishStatus(const std::string & status)
  {
    std_msgs::msg::String message;
    message.data = status;
    status_publisher_->publish(message);
    RCLCPP_INFO(node().get_logger(), "Control status: %s", status.c_str());
  }

private:
  void receiveSetpoint(const geometry_msgs::msg::PoseStamped & message)
  {
    if (!isActive() || !isArmed()) {
      RCLCPP_WARN(
        node().get_logger(),
        "Ignoring %s: DRN Control must be active and armed",
        kSetpointTopic);
      return;
    }

    if (message.header.frame_id != command_frame_) {
      RCLCPP_WARN(
        node().get_logger(),
        "Ignoring %s in frame '%s'; expected '%s'",
        kSetpointTopic,
        message.header.frame_id.c_str(),
        command_frame_.c_str());
      return;
    }

    std::string error;
    auto target = poseEnuToNed(message.pose, max_abs_position_m_, &error);
    if (!target.has_value()) {
      RCLCPP_WARN(
        node().get_logger(),
        "Ignoring invalid %s: %s",
        kSetpointTopic,
        error.c_str());
      return;
    }

    target_ = std::move(target);
    publishStatus("tracking_setpoint");
  }

  const std::string command_frame_;
  const float max_abs_position_m_;
  const float max_horizontal_speed_m_s_;
  const float max_vertical_speed_m_s_;
  const float max_heading_rate_rad_s_;

  std::shared_ptr<px4_ros2::MulticopterGotoSetpointType> goto_setpoint_;
  std::shared_ptr<px4_ros2::OdometryLocalPosition> local_position_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_publisher_;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr setpoint_subscription_;
  std::optional<NedSetpoint> target_;
};

class DrnControlExecutor : public px4_ros2::ModeExecutorBase
{
public:
  explicit DrnControlExecutor(DrnControlMode & owned_mode)
  : ModeExecutorBase(
      Settings{}.activate(Settings::Activation::ActivateAlways),
      owned_mode),
    mode_(owned_mode),
    node_(owned_mode.node())
  {
    vehicle_command_client_ =
      node_.create_client<px4_msgs::srv::VehicleCommand>("/fmu/vehicle_command");
    activate_service_ = createTriggerService(
      "/drn/control/activate",
      [this](std_srvs::srv::Trigger::Response & response) {
        requestActivate(response);
      });
    takeoff_service_ = createTriggerService(
      "/drn/control/takeoff",
      [this](std_srvs::srv::Trigger::Response & response) {
        requestTakeoff(response);
      });
    hold_service_ = createTriggerService(
      "/drn/control/hold",
      [this](std_srvs::srv::Trigger::Response & response) {
        requestHold(response);
      });
    land_service_ = createTriggerService(
      "/drn/control/land",
      [this](std_srvs::srv::Trigger::Response & response) {
        requestLand(response);
      });
    rtl_service_ = createTriggerService(
      "/drn/control/rtl",
      [this](std_srvs::srv::Trigger::Response & response) {
        requestRtl(response);
      });

    // NodeWithModeExecutor spins only after registration completes, so this
    // one-shot timer turns the constructor's startup status into a confirmed
    // registered state on the first executor cycle.
    registration_status_timer_ = node_.create_wall_timer(
      std::chrono::milliseconds(1),
      [this]() {
        if (mode_.isActive()) {
          mode_.publishStatus("holding");
        } else if (isInCharge()) {
          mode_.publishStatus(isArmed() ? "ready_armed" : "ready_disarmed");
        } else {
          mode_.publishStatus("inactive");
        }
        registration_status_timer_->cancel();
      });
  }

  void onActivate() override
  {
    ++generation_;
    operation_ = Operation::Idle;
    mode_.publishStatus(isArmed() ? "ready_armed" : "ready_disarmed");
  }

  void onDeactivate(DeactivateReason reason) override
  {
    ++generation_;
    operation_ = Operation::Idle;
    mode_.publishStatus(
      reason == DeactivateReason::FailsafeActivated ?
      "inactive: failsafe activated" :
      "inactive");
  }

private:
  enum class Operation
  {
    Idle,
    Activating,
    Arming,
    TakingOff,
    Landing,
    Returning
  };

  using TriggerResponse = std_srvs::srv::Trigger::Response;
  using TriggerHandler = std::function<void (TriggerResponse &)>;

  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr createTriggerService(
    const std::string & name,
    TriggerHandler handler)
  {
    return node_.create_service<std_srvs::srv::Trigger>(
      name,
      [handler = std::move(handler)](
        std_srvs::srv::Trigger::Request::SharedPtr,
        std_srvs::srv::Trigger::Response::SharedPtr response)
      {
        handler(*response);
      });
  }

  bool beginRequest(Operation operation, TriggerResponse & response)
  {
    if (!isInCharge()) {
      response.success = false;
      response.message = "Select the DRN Control flight mode first";
      return false;
    }
    if (operation_ != Operation::Idle) {
      response.success = false;
      response.message = "Another control operation is already in progress";
      return false;
    }

    operation_ = operation;
    response.success = true;
    response.message = "Request accepted; monitor /drn/control/status";
    return true;
  }

  void requestActivate(TriggerResponse & response)
  {
    if (isInCharge()) {
      response.success = true;
      response.message = "DRN Control is already active";
      return;
    }
    if (isArmed()) {
      response.success = false;
      response.message = "Activate DRN Control only while the vehicle is disarmed";
      return;
    }
    if (operation_ != Operation::Idle) {
      response.success = false;
      response.message = "Another control operation is already in progress";
      return;
    }

    operation_ = Operation::Activating;
    const std::uint64_t generation = ++generation_;
    mode_.publishStatus("activating");

    if (!vehicle_command_client_->service_is_ready()) {
      operation_ = Operation::Idle;
      response.success = false;
      response.message = "PX4 vehicle command service is unavailable";
      mode_.publishStatus("error: PX4 vehicle command service unavailable");
      return;
    }

    auto request = std::make_shared<px4_msgs::srv::VehicleCommand::Request>();
    auto & command = request->request;
    command.timestamp =
      static_cast<std::uint64_t>(node_.get_clock()->now().nanoseconds() / 1000);
    command.param1 = static_cast<float>(mode_.id());
    command.command = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_SET_NAV_STATE;
    command.target_system = 1;
    command.target_component = 1;
    command.source_system = 1;
    command.source_component = 1;
    command.from_external = true;

    vehicle_command_client_->async_send_request(
      request,
      [this, generation](
        rclcpp::Client<px4_msgs::srv::VehicleCommand>::SharedFuture future)
      {
        if (!isCurrent(generation)) {
          return;
        }

        try {
          const auto & reply = future.get()->reply;
          if (reply.result ==
          px4_msgs::msg::VehicleCommandAck::VEHICLE_CMD_RESULT_ACCEPTED)
          {
            mode_.publishStatus("activation_accepted");
          } else {
            operation_ = Operation::Idle;
            mode_.publishStatus(
              "error: activation rejected by PX4 (result " +
              std::to_string(reply.result) + ")");
          }
        } catch (const std::exception & exception) {
          operation_ = Operation::Idle;
          mode_.publishStatus(
            "error: activation request failed: " + std::string(exception.what()));
        }
      });

    response.success = true;
    response.message = "Activation requested; monitor /drn/control/status";
  }

  void requestTakeoff(TriggerResponse & response)
  {
    if (isArmed()) {
      response.success = false;
      response.message = "Takeoff requires a disarmed vehicle";
      return;
    }
    if (!beginRequest(Operation::Arming, response)) {
      return;
    }

    const std::uint64_t generation = ++generation_;
    mode_.publishStatus("arming");
    arm(
      [this, generation](px4_ros2::Result result) {
        if (!isCurrent(generation)) {
          return;
        }
        if (result != px4_ros2::Result::Success) {
          finishWithResult("arming", result);
          return;
        }
        startTakeoff(generation);
      });
  }

  void startTakeoff(std::uint64_t generation)
  {
    operation_ = Operation::TakingOff;
    mode_.publishStatus("taking_off");
    takeoff(
      [this, generation](px4_ros2::Result result) {
        if (!isCurrent(generation)) {
          return;
        }
        if (result != px4_ros2::Result::Success) {
          finishWithResult("takeoff", result);
          return;
        }
        scheduleHold(generation);
      });
  }

  void requestHold(TriggerResponse & response)
  {
    if (!isArmed()) {
      response.success = false;
      response.message = "Hold requires an armed vehicle";
      return;
    }
    if (!beginRequest(Operation::Idle, response)) {
      return;
    }

    const std::uint64_t generation = ++generation_;
    if (mode_.isActive()) {
      if (!mode_.captureCurrentTarget()) {
        response.success = false;
        response.message = "Local position is unavailable";
        mode_.publishStatus("error: local position unavailable");
        return;
      }
      mode_.publishStatus("holding");
      return;
    }
    scheduleHold(generation);
  }

  void scheduleHold(std::uint64_t generation)
  {
    operation_ = Operation::Idle;
    mode_.publishStatus("activating_hold");
    scheduleMode(
      mode_.id(),
      [this, generation](px4_ros2::Result result) {
        if (!isCurrent(generation)) {
          return;
        }
        if (result != px4_ros2::Result::Deactivated) {
          finishWithResult("hold", result);
        }
      });
  }

  void requestLand(TriggerResponse & response)
  {
    if (!isArmed()) {
      response.success = false;
      response.message = "Vehicle is already disarmed";
      return;
    }
    if (!beginRequest(Operation::Landing, response)) {
      return;
    }

    const std::uint64_t generation = ++generation_;
    mode_.publishStatus("landing");
    land(
      [this, generation](px4_ros2::Result result) {
        if (!isCurrent(generation)) {
          return;
        }
        if (result != px4_ros2::Result::Success) {
          finishWithResult("land", result);
          return;
        }
        waitForDisarm(generation, "landed");
      });
  }

  void requestRtl(TriggerResponse & response)
  {
    if (!isArmed()) {
      response.success = false;
      response.message = "Vehicle is already disarmed";
      return;
    }
    if (!beginRequest(Operation::Returning, response)) {
      return;
    }

    const std::uint64_t generation = ++generation_;
    mode_.publishStatus("returning_to_launch");
    rtl(
      [this, generation](px4_ros2::Result result) {
        if (!isCurrent(generation)) {
          return;
        }
        if (result != px4_ros2::Result::Success) {
          finishWithResult("rtl", result);
          return;
        }
        waitForDisarm(generation, "rtl_complete");
      });
  }

  void waitForDisarm(std::uint64_t generation, const std::string & final_status)
  {
    mode_.publishStatus("waiting_for_disarm");
    waitUntilDisarmed(
      [this, generation, final_status](px4_ros2::Result result) {
        if (!isCurrent(generation)) {
          return;
        }
        operation_ = Operation::Idle;
        if (result == px4_ros2::Result::Success) {
          mode_.publishStatus(final_status);
        } else {
          finishWithResult("disarm wait", result);
        }
      });
  }

  bool isCurrent(std::uint64_t generation) const
  {
    return generation == generation_;
  }

  void finishWithResult(const std::string & operation, px4_ros2::Result result)
  {
    operation_ = Operation::Idle;
    const std::string status =
      "error: " + operation + " " + px4_ros2::resultToString(result);
    mode_.publishStatus(status);
  }

  DrnControlMode & mode_;
  rclcpp::Node & node_;
  Operation operation_{Operation::Idle};
  std::uint64_t generation_{0};

  rclcpp::Client<px4_msgs::srv::VehicleCommand>::SharedPtr vehicle_command_client_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr activate_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr takeoff_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr hold_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr land_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr rtl_service_;
  rclcpp::TimerBase::SharedPtr registration_status_timer_;
};

using DrnControlNode =
  px4_ros2::NodeWithModeExecutor<DrnControlExecutor, DrnControlMode>;

}  // namespace drn_control

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);

  try {
    rclcpp::spin(std::make_shared<drn_control::DrnControlNode>("drn_control"));
  } catch (const std::exception & exception) {
    RCLCPP_ERROR(
      rclcpp::get_logger("drn_control"),
      "Control node stopped: %s",
      exception.what());
  }

  if (rclcpp::ok()) {
    rclcpp::shutdown();
  }
  return 0;
}
