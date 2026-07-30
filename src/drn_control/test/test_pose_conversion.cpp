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
#include <cmath>
#include <limits>
#include <string>

#include <drn_control/pose_conversion.hpp>

namespace
{

constexpr float kTolerance = 1.0e-5F;

geometry_msgs::msg::Pose poseAt(double east, double north, double up)
{
  geometry_msgs::msg::Pose pose;
  pose.position.x = east;
  pose.position.y = north;
  pose.position.z = up;
  return pose;
}

TEST(PoseConversion, ConvertsEnuPositionToNed)
{
  const auto result = drn_control::poseEnuToNed(poseAt(1.0, 2.0, 3.0), 100.0);

  ASSERT_TRUE(result.has_value());
  EXPECT_NEAR(result->position_m.x(), 2.0F, kTolerance);
  EXPECT_NEAR(result->position_m.y(), 1.0F, kTolerance);
  EXPECT_NEAR(result->position_m.z(), -3.0F, kTolerance);
}

TEST(PoseConversion, LeavesHeadingUnconstrainedForZeroQuaternion)
{
  auto pose = poseAt(0.0, 0.0, 0.0);
  pose.orientation.w = 0.0;
  const auto result = drn_control::poseEnuToNed(pose, 100.0);

  ASSERT_TRUE(result.has_value());
  EXPECT_FALSE(result->heading_rad.has_value());
}

TEST(PoseConversion, ConvertsEastFacingEnuHeadingToNed)
{
  auto pose = poseAt(0.0, 0.0, 0.0);
  pose.orientation.w = 1.0;

  const auto result = drn_control::poseEnuToNed(pose, 100.0);

  ASSERT_TRUE(result.has_value());
  ASSERT_TRUE(result->heading_rad.has_value());
  EXPECT_NEAR(*result->heading_rad, static_cast<float>(M_PI_2), kTolerance);
}

TEST(PoseConversion, ConvertsNorthFacingEnuHeadingToNed)
{
  auto pose = poseAt(0.0, 0.0, 0.0);
  pose.orientation.z = std::sin(M_PI_4);
  pose.orientation.w = std::cos(M_PI_4);

  const auto result = drn_control::poseEnuToNed(pose, 100.0);

  ASSERT_TRUE(result.has_value());
  ASSERT_TRUE(result->heading_rad.has_value());
  EXPECT_NEAR(*result->heading_rad, 0.0F, kTolerance);
}

TEST(PoseConversion, RejectsInvalidAndOutOfBoundsPositions)
{
  std::string error;
  auto invalid = poseAt(std::numeric_limits<double>::quiet_NaN(), 0.0, 0.0);
  EXPECT_FALSE(drn_control::poseEnuToNed(invalid, 100.0, &error).has_value());
  EXPECT_FALSE(error.empty());

  error.clear();
  auto out_of_bounds = poseAt(101.0, 0.0, 0.0);
  EXPECT_FALSE(drn_control::poseEnuToNed(out_of_bounds, 100.0, &error).has_value());
  EXPECT_FALSE(error.empty());
}

TEST(PoseConversion, RejectsTiltedOrientation)
{
  auto pose = poseAt(0.0, 0.0, 0.0);
  pose.orientation.x = std::sin(0.25);
  pose.orientation.w = std::cos(0.25);

  std::string error;
  EXPECT_FALSE(drn_control::poseEnuToNed(pose, 100.0, &error).has_value());
  EXPECT_EQ(error, "orientation roll and pitch must be near zero");
}

}  // namespace
