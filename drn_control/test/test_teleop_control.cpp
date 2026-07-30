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

#include <gtest/gtest.h>
#include <chrono>
#include <cmath>
#include <limits>
#include <string>

#include <drn_control/teleop_control.hpp>

namespace
{

constexpr float kTolerance = 1.0e-5F;

TEST(TeleopControl, ParsesAndLimitsHorizontalVector)
{
  geometry_msgs::msg::Twist message;
  message.linear.x = 3.0;
  message.linear.y = 4.0;

  const auto command = drn_control::parseHorizontalTeleop(message, 2.0F);

  ASSERT_TRUE(command.has_value());
  EXPECT_NEAR(command->forward_m_s, 1.2F, kTolerance);
  EXPECT_NEAR(command->left_m_s, 1.6F, kTolerance);
}

TEST(TeleopControl, RejectsUnexpectedAndNonFiniteFields)
{
  geometry_msgs::msg::Twist message;
  message.angular.z = 0.1;
  std::string error;

  EXPECT_FALSE(drn_control::parseHorizontalTeleop(message, 2.0F, &error).has_value());
  EXPECT_EQ(error, "horizontal teleop accepts only linear.x and linear.y");

  message.angular.z = 0.0;
  message.linear.x = std::numeric_limits<double>::quiet_NaN();
  error.clear();
  EXPECT_FALSE(drn_control::parseHorizontalTeleop(message, 2.0F, &error).has_value());
  EXPECT_EQ(error, "teleop command contains a non-finite value");
}

TEST(TeleopControl, ParsesAndClampsVerticalYaw)
{
  geometry_msgs::msg::Twist message;
  message.linear.z = -3.0;
  message.angular.z = 2.0;

  const auto command = drn_control::parseVerticalYawTeleop(message, 1.0F, 0.8F);

  ASSERT_TRUE(command.has_value());
  EXPECT_NEAR(command->up_m_s, -1.0F, kTolerance);
  EXPECT_NEAR(command->yaw_rate_ccw_rad_s, 0.8F, kTolerance);
}

TEST(TeleopControl, ConvertsBodyFluVelocityAtNorthAndEastHeadings)
{
  drn_control::BodyTeleopCommand command;
  command.forward_m_s = 1.0F;
  command.left_m_s = 2.0F;
  command.up_m_s = 3.0F;

  const Eigen::Vector3f north = drn_control::bodyFluVelocityToNed(command, 0.0F);
  EXPECT_NEAR(north.x(), 1.0F, kTolerance);
  EXPECT_NEAR(north.y(), -2.0F, kTolerance);
  EXPECT_NEAR(north.z(), -3.0F, kTolerance);

  const Eigen::Vector3f east =
    drn_control::bodyFluVelocityToNed(command, static_cast<float>(M_PI_2));
  EXPECT_NEAR(east.x(), 2.0F, kTolerance);
  EXPECT_NEAR(east.y(), 1.0F, kTolerance);
  EXPECT_NEAR(east.z(), -3.0F, kTolerance);
}

TEST(TeleopControl, MixesFreshSourcesAndExpiresThemIndependently)
{
  using namespace std::chrono_literals;
  drn_control::TeleopCommandMixer mixer(300ms);
  const auto start = drn_control::TeleopCommandMixer::TimePoint{};

  drn_control::BodyTeleopCommand horizontal;
  horizontal.forward_m_s = 0.5F;
  mixer.updateHorizontal(horizontal, start);

  drn_control::BodyTeleopCommand vertical;
  vertical.up_m_s = 0.25F;
  mixer.updateVerticalYaw(vertical, start + 200ms);

  const auto combined = mixer.sample(start + 250ms);
  EXPECT_TRUE(combined.any_fresh);
  EXPECT_FALSE(combined.expired_nonzero);
  EXPECT_NEAR(combined.command.forward_m_s, 0.5F, kTolerance);
  EXPECT_NEAR(combined.command.up_m_s, 0.25F, kTolerance);

  const auto partially_expired = mixer.sample(start + 350ms);
  EXPECT_TRUE(partially_expired.any_fresh);
  EXPECT_TRUE(partially_expired.expired_nonzero);
  EXPECT_NEAR(partially_expired.command.forward_m_s, 0.0F, kTolerance);
  EXPECT_NEAR(partially_expired.command.up_m_s, 0.25F, kTolerance);
}

TEST(TeleopControl, ClearsCommandsAndWrapsHeading)
{
  using namespace std::chrono_literals;
  drn_control::TeleopCommandMixer mixer(300ms);
  const auto start = drn_control::TeleopCommandMixer::TimePoint{};

  drn_control::BodyTeleopCommand horizontal;
  horizontal.left_m_s = 0.5F;
  mixer.updateHorizontal(horizontal, start);
  ASSERT_TRUE(mixer.hasActiveCommand(start));

  mixer.clear();
  EXPECT_FALSE(mixer.hasActiveCommand(start));
  EXPECT_NEAR(
    drn_control::wrapAnglePi(static_cast<float>(2.5 * M_PI)),
    static_cast<float>(M_PI_2),
    kTolerance);
}

}  // namespace
