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

#pragma once

#include <Eigen/Geometry>
#include <cmath>
#include <optional>
#include <string>

#include <geometry_msgs/msg/pose.hpp>
#include <px4_ros2/utils/frame_conversion.hpp>
#include <px4_ros2/utils/geometry.hpp>

namespace drn_control
{

struct NedSetpoint
{
  Eigen::Vector3f position_m;
  std::optional<float> heading_rad;
};

inline std::optional<NedSetpoint> poseEnuToNed(
  const geometry_msgs::msg::Pose & pose,
  double max_abs_position_m,
  std::string * error = nullptr)
{
  const auto fail = [error](const std::string & message) -> std::optional<NedSetpoint> {
      if (error != nullptr) {
        *error = message;
      }
      return std::nullopt;
    };

  if (!std::isfinite(max_abs_position_m) || max_abs_position_m <= 0.0) {
    return fail("max_abs_position_m must be finite and positive");
  }

  const double coordinates[] = {pose.position.x, pose.position.y, pose.position.z};
  for (const double coordinate : coordinates) {
    if (!std::isfinite(coordinate)) {
      return fail("position contains a non-finite value");
    }
    if (std::abs(coordinate) > max_abs_position_m) {
      return fail("position exceeds max_abs_position_m");
    }
  }

  const Eigen::Vector3f position_enu{
    static_cast<float>(pose.position.x),
    static_cast<float>(pose.position.y),
    static_cast<float>(pose.position.z)};

  NedSetpoint setpoint{px4_ros2::positionEnuToNed(position_enu), std::nullopt};

  const double quaternion_values[] = {
    pose.orientation.w,
    pose.orientation.x,
    pose.orientation.y,
    pose.orientation.z};
  for (const double value : quaternion_values) {
    if (!std::isfinite(value)) {
      return fail("orientation contains a non-finite value");
    }
  }

  Eigen::Quaternionf orientation_enu{
    static_cast<float>(pose.orientation.w),
    static_cast<float>(pose.orientation.x),
    static_cast<float>(pose.orientation.y),
    static_cast<float>(pose.orientation.z)};
  const float norm = orientation_enu.norm();

  // A zero quaternion means the caller intentionally left heading unconstrained.
  if (norm < 1.0e-6F) {
    return setpoint;
  }

  orientation_enu.normalize();
  const Eigen::Vector3f rpy = px4_ros2::quaternionToEulerRpy(orientation_enu);
  constexpr float kMaxIgnoredTiltRad = 0.1F;
  if (std::abs(rpy.x()) > kMaxIgnoredTiltRad || std::abs(rpy.y()) > kMaxIgnoredTiltRad) {
    return fail("orientation roll and pitch must be near zero");
  }

  setpoint.heading_rad = px4_ros2::yawEnuToNed(rpy.z());
  return setpoint;
}

}  // namespace drn_control
