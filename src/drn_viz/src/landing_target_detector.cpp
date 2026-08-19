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

#include <algorithm>
#include <cmath>
#include <functional>
#include <memory>
#include <stdexcept>
#include <vector>

#include <cv_bridge/cv_bridge.h>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <opencv2/aruco.hpp>
#include <opencv2/calib3d.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/image_encodings.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <std_msgs/msg/bool.hpp>

namespace drn_viz
{

class LandingTargetDetector : public rclcpp::Node
{
public:
  LandingTargetDetector()
  : Node("landing_target_detector"),
    marker_id_(declare_parameter<int>("marker_id", 0)),
    dictionary_id_(declare_parameter<int>("dictionary_id", cv::aruco::DICT_4X4_250)),
    marker_size_m_(declare_parameter<double>("marker_size_m", 0.5)),
    publish_debug_image_(declare_parameter<bool>("publish_debug_image", true))
  {
    if (marker_id_ < 0) {
      throw std::invalid_argument("marker_id must be non-negative");
    }
    if (dictionary_id_ < cv::aruco::DICT_4X4_50 ||
      dictionary_id_ > cv::aruco::DICT_APRILTAG_36h11)
    {
      throw std::invalid_argument("dictionary_id is not a predefined OpenCV dictionary");
    }
    if (!std::isfinite(marker_size_m_) || marker_size_m_ <= 0.0) {
      throw std::invalid_argument("marker_size_m must be finite and positive");
    }

    dictionary_ = cv::aruco::getPredefinedDictionary(dictionary_id_);
    const auto qos = rclcpp::SensorDataQoS();
    pose_publisher_ = create_publisher<geometry_msgs::msg::PoseStamped>(
      "/drn/sensors/landing/target_pose", qos);
    visible_publisher_ = create_publisher<std_msgs::msg::Bool>(
      "/drn/sensors/landing/visible", qos);
    if (publish_debug_image_) {
      debug_publisher_ = create_publisher<sensor_msgs::msg::Image>(
        "/drn/sensors/landing/debug/image", qos);
    }
    camera_info_subscription_ = create_subscription<sensor_msgs::msg::CameraInfo>(
      "/drn/sensors/landing/camera_info", qos,
      std::bind(&LandingTargetDetector::receiveCameraInfo, this, std::placeholders::_1));
    image_subscription_ = create_subscription<sensor_msgs::msg::Image>(
      "/drn/sensors/landing/image_raw", qos,
      std::bind(&LandingTargetDetector::receiveImage, this, std::placeholders::_1));
  }

private:
  void receiveCameraInfo(const sensor_msgs::msg::CameraInfo::ConstSharedPtr message)
  {
    if (!std::isfinite(message->k[0]) || !std::isfinite(message->k[4]) ||
      message->k[0] <= 0.0 || message->k[4] <= 0.0)
    {
      RCLCPP_WARN_THROTTLE(
        get_logger(), *get_clock(), 2000, "Ignoring invalid landing camera calibration");
      return;
    }
    camera_matrix_ = cv::Mat(3, 3, CV_64F);
    std::copy(message->k.begin(), message->k.end(), camera_matrix_.ptr<double>());
    distortion_ = cv::Mat(
      static_cast<int>(message->d.size()), 1, CV_64F);
    if (!message->d.empty()) {
      std::copy(message->d.begin(), message->d.end(), distortion_.ptr<double>());
    }
  }

  void receiveImage(const sensor_msgs::msg::Image::ConstSharedPtr message)
  {
    std_msgs::msg::Bool visible;
    try {
      auto image = cv_bridge::toCvCopy(message, sensor_msgs::image_encodings::BGR8);
      std::vector<int> ids;
      std::vector<std::vector<cv::Point2f>> corners;
      cv::aruco::detectMarkers(image->image, dictionary_, corners, ids);
      if (!ids.empty()) {
        cv::aruco::drawDetectedMarkers(image->image, corners, ids);
      }

      const auto marker = std::find(ids.begin(), ids.end(), marker_id_);
      if (marker != ids.end() && !camera_matrix_.empty()) {
        const std::size_t index = static_cast<std::size_t>(marker - ids.begin());
        const float half_size = static_cast<float>(marker_size_m_ * 0.5);
        const std::vector<cv::Point3f> object_points{
          {-half_size, half_size, 0.0F},
          {half_size, half_size, 0.0F},
          {half_size, -half_size, 0.0F},
          {-half_size, -half_size, 0.0F}};
        cv::Vec3d rotation;
        cv::Vec3d translation;
        const bool solved = cv::solvePnP(
          object_points, corners[index], camera_matrix_, distortion_,
          rotation, translation, false, cv::SOLVEPNP_IPPE_SQUARE);
        if (solved && translation[2] > 0.0 && cv::checkRange(translation)) {
          visible.data = true;
          geometry_msgs::msg::PoseStamped pose;
          pose.header = message->header;
          pose.header.frame_id = "landing_camera_optical";
          pose.pose.position.x = translation[0];
          pose.pose.position.y = translation[1];
          pose.pose.position.z = translation[2];
          pose.pose.orientation.w = 1.0;
          pose_publisher_->publish(pose);
          cv::drawFrameAxes(
            image->image, camera_matrix_, distortion_, rotation, translation,
            static_cast<float>(marker_size_m_ * 0.5));
        }
      }
      visible_publisher_->publish(visible);
      if (debug_publisher_) {
        debug_publisher_->publish(*image->toImageMsg());
      }
    } catch (const cv_bridge::Exception & exception) {
      visible_publisher_->publish(visible);
      RCLCPP_ERROR_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Landing camera conversion failed: %s", exception.what());
    } catch (const cv::Exception & exception) {
      visible_publisher_->publish(visible);
      RCLCPP_ERROR_THROTTLE(
        get_logger(), *get_clock(), 2000,
        "Landing target detection failed: %s", exception.what());
    }
  }

  const int marker_id_;
  const int dictionary_id_;
  const double marker_size_m_;
  const bool publish_debug_image_;
  cv::Ptr<cv::aruco::Dictionary> dictionary_;
  cv::Mat camera_matrix_;
  cv::Mat distortion_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_publisher_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr visible_publisher_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr debug_publisher_;
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr camera_info_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_subscription_;
};

}  // namespace drn_viz

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<drn_viz::LandingTargetDetector>());
  rclcpp::shutdown();
  return 0;
}
