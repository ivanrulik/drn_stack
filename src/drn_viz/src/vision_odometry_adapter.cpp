#include <memory>
#include <string>
#include <utility>

#include <nav_msgs/msg/odometry.hpp>
#include <rclcpp/rclcpp.hpp>

namespace drn_viz
{

class VisionOdometryAdapter : public rclcpp::Node
{
public:
  VisionOdometryAdapter()
  : Node("vision_odometry_adapter")
  {
    const auto input_topic = declare_parameter<std::string>(
      "input_topic", "/drn/internal/vision/odometry");
    const auto output_topic = declare_parameter<std::string>(
      "output_topic", "/drn/sensors/vision/odometry");
    world_frame_ = declare_parameter<std::string>("world_frame", "map");
    base_frame_ = declare_parameter<std::string>("base_frame", "base_link");

    const auto qos = rclcpp::SensorDataQoS();
    publisher_ = create_publisher<nav_msgs::msg::Odometry>(output_topic, qos);
    subscription_ = create_subscription<nav_msgs::msg::Odometry>(
      input_topic,
      qos,
      [this](nav_msgs::msg::Odometry::UniquePtr message) {
        message->header.frame_id = world_frame_;
        message->child_frame_id = base_frame_;
        publisher_->publish(std::move(message));
      });
  }

private:
  std::string world_frame_;
  std::string base_frame_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr publisher_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr subscription_;
};

}  // namespace drn_viz

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<drn_viz::VisionOdometryAdapter>());
  rclcpp::shutdown();
  return 0;
}
