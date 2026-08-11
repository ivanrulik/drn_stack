#include <array>
#include <chrono>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <visualization_msgs/msg/marker.hpp>
#include <visualization_msgs/msg/marker_array.hpp>

namespace drn_viz
{

struct Wall
{
  double x;
  double y;
  double z;
  double size_x;
  double size_y;
  double size_z;
};

constexpr std::array<Wall, 4> WALLS{{
  {5.0, 0.0, 7.5, 1.0, 20.0, 15.0},
  {-3.0, 5.0, 7.5, 10.0, 1.0, 15.0},
  {13.0, -10.0, 7.5, 17.0, 1.0, 15.0},
  {12.0, 0.0, 7.5, 1.0, 20.0, 15.0},
}};

class LidarWorldMarkers : public rclcpp::Node
{
public:
  LidarWorldMarkers()
  : Node("lidar_world_markers")
  {
    frame_id_ = declare_parameter<std::string>("frame_id", "map");
    const auto topic = declare_parameter<std::string>(
      "topic", "/drn/viz/lidar/walls");

    publisher_ = create_publisher<visualization_msgs::msg::MarkerArray>(
      topic, rclcpp::QoS(1).reliable().transient_local());
    timer_ = create_wall_timer(
      std::chrono::seconds(1), [this]() {publish_walls();});
    publish_walls();
  }

private:
  void publish_walls()
  {
    visualization_msgs::msg::MarkerArray message;
    message.markers.reserve(WALLS.size());

    for (std::size_t index = 0; index < WALLS.size(); ++index) {
      const auto & wall = WALLS[index];
      visualization_msgs::msg::Marker marker;
      marker.header.frame_id = frame_id_;
      marker.header.stamp = now();
      marker.ns = "lidar_world_walls";
      marker.id = static_cast<int>(index);
      marker.type = visualization_msgs::msg::Marker::CUBE;
      marker.action = visualization_msgs::msg::Marker::ADD;
      marker.pose.position.x = wall.x;
      marker.pose.position.y = wall.y;
      marker.pose.position.z = wall.z;
      marker.pose.orientation.w = 1.0;
      marker.scale.x = wall.size_x;
      marker.scale.y = wall.size_y;
      marker.scale.z = wall.size_z;
      marker.color.r = 0.15F;
      marker.color.g = 0.45F;
      marker.color.b = 0.80F;
      marker.color.a = 0.35F;
      marker.frame_locked = true;
      message.markers.push_back(marker);
    }

    publisher_->publish(message);
  }

  std::string frame_id_;
  rclcpp::Publisher<visualization_msgs::msg::MarkerArray>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace drn_viz

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<drn_viz::LidarWorldMarkers>());
  rclcpp::shutdown();
  return 0;
}
