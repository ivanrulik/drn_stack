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
#include <algorithm>
#include <cmath>

namespace drn_control
{

struct PrecisionLandingConfig
{
  float horizontal_gain{0.8F};
  float max_horizontal_speed_m_s{0.6F};
  float descent_speed_m_s{0.3F};
  float alignment_tolerance_m{0.15F};
};

struct PrecisionLandingCommand
{
  Eigen::Vector3f velocity_ned_m_s{Eigen::Vector3f::Zero()};
  bool aligned{false};
};

inline bool finitePositive(float value)
{
  return std::isfinite(value) && value > 0.0F;
}

enum class PrecisionLandingAction
{
  Hold,
  Land,
  Rtl,
  Abort,
  Other
};

inline bool precisionLandingCanBePreemptedBy(PrecisionLandingAction action)
{
  return action != PrecisionLandingAction::Other;
}

inline bool validPrecisionLandingTarget(
  const Eigen::Vector3f & target_optical_m,
  float min_distance_m,
  float max_distance_m)
{
  const float distance_m = target_optical_m.norm();
  return target_optical_m.allFinite() && finitePositive(min_distance_m) &&
         finitePositive(max_distance_m) && min_distance_m < max_distance_m &&
         std::isfinite(distance_m) && distance_m >= min_distance_m &&
         distance_m <= max_distance_m && target_optical_m.z() > 0.0F;
}

inline bool precisionLandingTargetFresh(double age_s, float timeout_s)
{
  return std::isfinite(age_s) && age_s >= 0.0 && finitePositive(timeout_s) &&
         age_s <= timeout_s;
}

inline Eigen::Vector3f opticalTargetToBodyFrd(
  const Eigen::Vector3f & target_optical_m,
  const Eigen::Vector3f & camera_position_body_frd_m)
{
  // REP 103 optical is x-right, y-down, z-forward. The precision-landing
  // camera points down, with the top of its image aligned to vehicle forward.
  const Eigen::Vector3f target_from_camera_body_frd{
    -target_optical_m.y(), target_optical_m.x(), target_optical_m.z()};
  return camera_position_body_frd_m + target_from_camera_body_frd;
}

inline Eigen::Vector3f bodyFrdTargetToNed(
  const Eigen::Vector3f & target_body_frd_m,
  const Eigen::Quaternionf & attitude_body_frd_to_ned)
{
  return attitude_body_frd_to_ned.normalized() * target_body_frd_m;
}

inline PrecisionLandingCommand precisionLandingCommand(
  const Eigen::Vector3f & target_offset_ned_m,
  bool descent_enabled,
  const PrecisionLandingConfig & config)
{
  PrecisionLandingCommand command;
  Eigen::Vector2f horizontal{
    target_offset_ned_m.x(), target_offset_ned_m.y()};
  command.aligned = horizontal.norm() <= config.alignment_tolerance_m;

  horizontal *= config.horizontal_gain;
  const float speed = horizontal.norm();
  if (speed > config.max_horizontal_speed_m_s) {
    horizontal *= config.max_horizontal_speed_m_s / speed;
  }

  command.velocity_ned_m_s.x() = horizontal.x();
  command.velocity_ned_m_s.y() = horizontal.y();
  command.velocity_ned_m_s.z() = descent_enabled ? config.descent_speed_m_s : 0.0F;
  return command;
}

}  // namespace drn_control
