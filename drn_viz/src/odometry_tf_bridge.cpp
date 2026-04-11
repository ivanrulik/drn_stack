#include <array>
#include <cmath>
#include <memory>
#include <string>

#include <Eigen/Geometry>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <px4_msgs/msg/vehicle_odometry.hpp>
#include <px4_ros_com/frame_transforms.h>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/qos.hpp>
#include <tf2_ros/transform_broadcaster.h>

class OdometryTfBridge : public rclcpp::Node
{
public:
  OdometryTfBridge()
  : Node("odometry_tf_bridge"),
    tx_(0.0), ty_(0.0), tz_(0.0), qw_(1.0), qx_(0.0), qy_(0.0), qz_(0.0)
  {
    this->declare_parameter<std::string>("odometry_topic", "/fmu/out/vehicle_odometry");
    this->declare_parameter<std::string>("world_frame", "map");
    this->declare_parameter<std::string>("base_frame", "base_link");

    const auto odometry_topic = this->get_parameter("odometry_topic").as_string();
    world_frame_ = this->get_parameter("world_frame").as_string();
    base_frame_ = this->get_parameter("base_frame").as_string();

    tf_broadcaster_ = std::make_unique<tf2_ros::TransformBroadcaster>(*this);

    auto qos = rclcpp::QoS(rclcpp::KeepLast(10));
    qos.reliability(RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT);
    qos.durability(RMW_QOS_POLICY_DURABILITY_VOLATILE);

    sub_ = this->create_subscription<px4_msgs::msg::VehicleOdometry>(
      odometry_topic,
      qos,
      std::bind(&OdometryTfBridge::odometryCb, this, std::placeholders::_1));

    timer_ = this->create_wall_timer(
      std::chrono::milliseconds(50),
      std::bind(&OdometryTfBridge::publishTf, this));

    RCLCPP_INFO(
      this->get_logger(),
      "Publishing TF %s -> %s from %s",
      world_frame_.c_str(),
      base_frame_.c_str(),
      odometry_topic.c_str());
  }

private:
  static bool hasNan(const std::array<float, 3> &v)
  {
    return std::isnan(v[0]) || std::isnan(v[1]) || std::isnan(v[2]);
  }

  static bool hasNanQuat(const std::array<float, 4> &q)
  {
    return std::isnan(q[0]) || std::isnan(q[1]) || std::isnan(q[2]) || std::isnan(q[3]);
  }

  void odometryCb(const px4_msgs::msg::VehicleOdometry::SharedPtr msg)
  {
    const std::array<float, 3> pos_ned{msg->position[0], msg->position[1], msg->position[2]};
    if (hasNan(pos_ned)) {
      return;
    }

    const Eigen::Vector3d pos_ned_eig(pos_ned[0], pos_ned[1], pos_ned[2]);
    const Eigen::Vector3d pos_enu = px4_ros_com::frame_transforms::ned_to_enu_local_frame(pos_ned_eig);

    tx_ = static_cast<double>(pos_enu.x());
    ty_ = static_cast<double>(pos_enu.y());
    tz_ = static_cast<double>(pos_enu.z());

    const std::array<float, 4> q_px4{msg->q[0], msg->q[1], msg->q[2], msg->q[3]};
    if (!hasNanQuat(q_px4)) {
      const auto q_ned = px4_ros_com::frame_transforms::utils::quaternion::array_to_eigen_quat(q_px4);
      const auto q_enu = px4_ros_com::frame_transforms::px4_to_ros_orientation(q_ned);

      qw_ = static_cast<double>(q_enu.w());
      qx_ = static_cast<double>(q_enu.x());
      qy_ = static_cast<double>(q_enu.y());
      qz_ = static_cast<double>(q_enu.z());
    } else {
      qw_ = 1.0;
      qx_ = 0.0;
      qy_ = 0.0;
      qz_ = 0.0;
    }
  }

  void publishTf()
  {
    geometry_msgs::msg::TransformStamped tf_msg;
    tf_msg.header.stamp = this->get_clock()->now();
    tf_msg.header.frame_id = world_frame_;
    tf_msg.child_frame_id = base_frame_;

    tf_msg.transform.translation.x = tx_;
    tf_msg.transform.translation.y = ty_;
    tf_msg.transform.translation.z = tz_;

    tf_msg.transform.rotation.w = qw_;
    tf_msg.transform.rotation.x = qx_;
    tf_msg.transform.rotation.y = qy_;
    tf_msg.transform.rotation.z = qz_;

    tf_broadcaster_->sendTransform(tf_msg);
  }

  std::string world_frame_;
  std::string base_frame_;

  double tx_;
  double ty_;
  double tz_;
  double qw_;
  double qx_;
  double qy_;
  double qz_;

  rclcpp::Subscription<px4_msgs::msg::VehicleOdometry>::SharedPtr sub_;
  rclcpp::TimerBase::SharedPtr timer_;
  std::unique_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<OdometryTfBridge>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
