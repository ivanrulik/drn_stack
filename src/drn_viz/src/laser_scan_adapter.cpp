#include <memory>
#include <string>
#include <utility>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp/qos.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>

namespace drn_viz
{

class LaserScanAdapter : public rclcpp::Node
{
public:
  LaserScanAdapter()
  : Node("laser_scan_adapter")
  {
    const auto input_topic = declare_parameter<std::string>(
      "input_topic", "/drn/internal/lidar/scan");
    const auto output_topic = declare_parameter<std::string>(
      "output_topic", "/drn/sensors/lidar/scan");
    output_frame_ = declare_parameter<std::string>("output_frame", "lidar_link");

    publisher_ = create_publisher<sensor_msgs::msg::LaserScan>(
      output_topic, rclcpp::SensorDataQoS());
    subscription_ = create_subscription<sensor_msgs::msg::LaserScan>(
      input_topic,
      rclcpp::SensorDataQoS(),
      [this](sensor_msgs::msg::LaserScan::UniquePtr message) {
        message->header.frame_id = output_frame_;
        publisher_->publish(std::move(message));
      });
  }

private:
  std::string output_frame_;
  rclcpp::Publisher<sensor_msgs::msg::LaserScan>::SharedPtr publisher_;
  rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr subscription_;
};

}  // namespace drn_viz

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<drn_viz::LaserScanAdapter>());
  rclcpp::shutdown();
  return 0;
}
