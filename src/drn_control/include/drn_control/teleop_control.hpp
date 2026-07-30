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

#include <Eigen/Core>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iterator>
#include <optional>
#include <string>

#include <geometry_msgs/msg/twist.hpp>

namespace drn_control
{

struct BodyTeleopCommand
{
  float forward_m_s{0.0F};
  float left_m_s{0.0F};
  float up_m_s{0.0F};
  float yaw_rate_ccw_rad_s{0.0F};

  bool isZero(float epsilon = 1.0e-5F) const
  {
    return std::abs(forward_m_s) <= epsilon &&
           std::abs(left_m_s) <= epsilon &&
           std::abs(up_m_s) <= epsilon &&
           std::abs(yaw_rate_ccw_rad_s) <= epsilon;
  }
};

struct TeleopSample
{
  BodyTeleopCommand command;
  bool any_fresh{false};
  bool expired_nonzero{false};
};

inline bool allFinite(const geometry_msgs::msg::Twist & message)
{
  const double values[] = {
    message.linear.x,
    message.linear.y,
    message.linear.z,
    message.angular.x,
    message.angular.y,
    message.angular.z};
  return std::all_of(
    std::begin(values),
    std::end(values),
    [](double value) {return std::isfinite(value);});
}

inline bool approximatelyZero(double value)
{
  return std::abs(value) <= 1.0e-6;
}

inline std::optional<BodyTeleopCommand> parseHorizontalTeleop(
  const geometry_msgs::msg::Twist & message,
  float max_horizontal_speed_m_s,
  std::string * error = nullptr)
{
  const auto fail = [error](const std::string & message_text)
    -> std::optional<BodyTeleopCommand>
    {
      if (error != nullptr) {
        *error = message_text;
      }
      return std::nullopt;
    };

  if (!std::isfinite(max_horizontal_speed_m_s) || max_horizontal_speed_m_s <= 0.0F) {
    return fail("max_horizontal_speed_m_s must be finite and positive");
  }
  if (!allFinite(message)) {
    return fail("teleop command contains a non-finite value");
  }
  if (!approximatelyZero(message.linear.z) ||
    !approximatelyZero(message.angular.x) ||
    !approximatelyZero(message.angular.y) ||
    !approximatelyZero(message.angular.z))
  {
    return fail("horizontal teleop accepts only linear.x and linear.y");
  }

  Eigen::Vector2f horizontal{
    static_cast<float>(message.linear.x),
    static_cast<float>(message.linear.y)};
  const float norm = horizontal.norm();
  if (norm > max_horizontal_speed_m_s) {
    horizontal *= max_horizontal_speed_m_s / norm;
  }

  BodyTeleopCommand command;
  command.forward_m_s = horizontal.x();
  command.left_m_s = horizontal.y();
  return command;
}

inline std::optional<BodyTeleopCommand> parseVerticalYawTeleop(
  const geometry_msgs::msg::Twist & message,
  float max_vertical_speed_m_s,
  float max_heading_rate_rad_s,
  std::string * error = nullptr)
{
  const auto fail = [error](const std::string & message_text)
    -> std::optional<BodyTeleopCommand>
    {
      if (error != nullptr) {
        *error = message_text;
      }
      return std::nullopt;
    };

  if (!std::isfinite(max_vertical_speed_m_s) || max_vertical_speed_m_s <= 0.0F) {
    return fail("max_vertical_speed_m_s must be finite and positive");
  }
  if (!std::isfinite(max_heading_rate_rad_s) || max_heading_rate_rad_s <= 0.0F) {
    return fail("max_heading_rate_rad_s must be finite and positive");
  }
  if (!allFinite(message)) {
    return fail("teleop command contains a non-finite value");
  }
  if (!approximatelyZero(message.linear.x) ||
    !approximatelyZero(message.linear.y) ||
    !approximatelyZero(message.angular.x) ||
    !approximatelyZero(message.angular.y))
  {
    return fail("vertical/yaw teleop accepts only linear.z and angular.z");
  }

  BodyTeleopCommand command;
  command.up_m_s = std::clamp(
    static_cast<float>(message.linear.z),
    -max_vertical_speed_m_s,
    max_vertical_speed_m_s);
  command.yaw_rate_ccw_rad_s = std::clamp(
    static_cast<float>(message.angular.z),
    -max_heading_rate_rad_s,
    max_heading_rate_rad_s);
  return command;
}

inline Eigen::Vector3f bodyFluVelocityToNed(
  const BodyTeleopCommand & command,
  float heading_ned_rad)
{
  const float cos_heading = std::cos(heading_ned_rad);
  const float sin_heading = std::sin(heading_ned_rad);
  return Eigen::Vector3f{
    command.forward_m_s * cos_heading + command.left_m_s * sin_heading,
    command.forward_m_s * sin_heading - command.left_m_s * cos_heading,
    -command.up_m_s};
}

inline float wrapAnglePi(float angle_rad)
{
  return std::atan2(std::sin(angle_rad), std::cos(angle_rad));
}

class TeleopCommandMixer
{
public:
  using Clock = std::chrono::steady_clock;
  using TimePoint = Clock::time_point;

  explicit TeleopCommandMixer(std::chrono::milliseconds timeout)
  : timeout_(timeout)
  {
  }

  void updateHorizontal(const BodyTeleopCommand & command, TimePoint received_at)
  {
    horizontal_ = TimedCommand{command, received_at};
  }

  void updateVerticalYaw(const BodyTeleopCommand & command, TimePoint received_at)
  {
    vertical_yaw_ = TimedCommand{command, received_at};
  }

  TeleopSample sample(TimePoint now) const
  {
    TeleopSample result;
    mergeHorizontal(horizontal_, now, result);
    mergeVerticalYaw(vertical_yaw_, now, result);
    return result;
  }

  bool hasActiveCommand(TimePoint now) const
  {
    return !sample(now).command.isZero();
  }

  void clear()
  {
    horizontal_.reset();
    vertical_yaw_.reset();
  }

private:
  struct TimedCommand
  {
    BodyTeleopCommand command;
    TimePoint received_at;
  };

  bool isFresh(const TimedCommand & command, TimePoint now) const
  {
    return now >= command.received_at && now - command.received_at <= timeout_;
  }

  void mergeHorizontal(
    const std::optional<TimedCommand> & timed,
    TimePoint now,
    TeleopSample & result) const
  {
    if (!timed.has_value()) {
      return;
    }
    if (isFresh(*timed, now)) {
      result.any_fresh = true;
      result.command.forward_m_s = timed->command.forward_m_s;
      result.command.left_m_s = timed->command.left_m_s;
    } else if (!timed->command.isZero()) {
      result.expired_nonzero = true;
    }
  }

  void mergeVerticalYaw(
    const std::optional<TimedCommand> & timed,
    TimePoint now,
    TeleopSample & result) const
  {
    if (!timed.has_value()) {
      return;
    }
    if (isFresh(*timed, now)) {
      result.any_fresh = true;
      result.command.up_m_s = timed->command.up_m_s;
      result.command.yaw_rate_ccw_rad_s = timed->command.yaw_rate_ccw_rad_s;
    } else if (!timed->command.isZero()) {
      result.expired_nonzero = true;
    }
  }

  const std::chrono::milliseconds timeout_;
  std::optional<TimedCommand> horizontal_;
  std::optional<TimedCommand> vertical_yaw_;
};

}  // namespace drn_control
