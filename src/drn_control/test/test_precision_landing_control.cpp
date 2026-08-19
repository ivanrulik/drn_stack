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

#include <Eigen/Geometry>
#include <drn_control/precision_landing_control.hpp>

namespace drn_control
{

TEST(PrecisionLandingControl, ConvertsDownwardOpticalTargetToBodyFrd)
{
  const Eigen::Vector3f target_optical{0.2F, -0.4F, 3.0F};
  const Eigen::Vector3f camera_position{0.0F, 0.0F, -0.1F};

  const Eigen::Vector3f target_body =
    opticalTargetToBodyFrd(target_optical, camera_position);

  EXPECT_NEAR(target_body.x(), 0.4F, 1.0e-6F);
  EXPECT_NEAR(target_body.y(), 0.2F, 1.0e-6F);
  EXPECT_NEAR(target_body.z(), 2.9F, 1.0e-6F);
}

TEST(PrecisionLandingControl, RotatesBodyOffsetIntoNed)
{
  constexpr float kQuarterTurn = 1.57079632679F;
  const Eigen::Quaternionf attitude(
    Eigen::AngleAxisf(kQuarterTurn, Eigen::Vector3f::UnitZ()));

  const Eigen::Vector3f target_ned =
    bodyFrdTargetToNed(Eigen::Vector3f{1.0F, 0.0F, 2.0F}, attitude);

  EXPECT_NEAR(target_ned.x(), 0.0F, 1.0e-6F);
  EXPECT_NEAR(target_ned.y(), 1.0F, 1.0e-6F);
  EXPECT_NEAR(target_ned.z(), 2.0F, 1.0e-6F);
}

TEST(PrecisionLandingControl, ClampsHorizontalVelocityAndGatesDescent)
{
  PrecisionLandingConfig config;
  config.horizontal_gain = 2.0F;
  config.max_horizontal_speed_m_s = 0.5F;
  config.descent_speed_m_s = 0.25F;
  config.alignment_tolerance_m = 0.1F;

  const auto aligning = precisionLandingCommand(
    Eigen::Vector3f{1.0F, 0.0F, 2.0F}, false, config);
  EXPECT_FALSE(aligning.aligned);
  EXPECT_NEAR(aligning.velocity_ned_m_s.x(), 0.5F, 1.0e-6F);
  EXPECT_FLOAT_EQ(aligning.velocity_ned_m_s.z(), 0.0F);

  const auto descending = precisionLandingCommand(
    Eigen::Vector3f{0.03F, 0.04F, 1.0F}, true, config);
  EXPECT_TRUE(descending.aligned);
  EXPECT_FLOAT_EQ(descending.velocity_ned_m_s.z(), 0.25F);
}

TEST(PrecisionLandingControl, ValidatesTargetBoundsAndFreshness)
{
  EXPECT_TRUE(
    validPrecisionLandingTarget(
      Eigen::Vector3f{0.1F, -0.1F, 2.0F}, 0.05F, 20.0F));
  EXPECT_FALSE(
    validPrecisionLandingTarget(
      Eigen::Vector3f{0.0F, 0.0F, -1.0F}, 0.05F, 20.0F));
  EXPECT_FALSE(
    validPrecisionLandingTarget(
      Eigen::Vector3f{0.0F, 0.0F, 21.0F}, 0.05F, 20.0F));

  EXPECT_TRUE(precisionLandingTargetFresh(0.49, 0.5F));
  EXPECT_FALSE(precisionLandingTargetFresh(0.51, 0.5F));
  EXPECT_FALSE(precisionLandingTargetFresh(-0.1, 0.5F));
}

TEST(PrecisionLandingControl, AllowsOnlySafetyActionsToPreempt)
{
  EXPECT_TRUE(precisionLandingCanBePreemptedBy(PrecisionLandingAction::Hold));
  EXPECT_TRUE(precisionLandingCanBePreemptedBy(PrecisionLandingAction::Land));
  EXPECT_TRUE(precisionLandingCanBePreemptedBy(PrecisionLandingAction::Rtl));
  EXPECT_TRUE(precisionLandingCanBePreemptedBy(PrecisionLandingAction::Abort));
  EXPECT_FALSE(precisionLandingCanBePreemptedBy(PrecisionLandingAction::Other));
}

}  // namespace drn_control
