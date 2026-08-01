"""Launch the inert DRN example inspection node."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Create the example project launch description."""
    heartbeat_period = LaunchConfiguration("heartbeat_period")
    return LaunchDescription(
        [
            DeclareLaunchArgument("heartbeat_period", default_value="1.0"),
            Node(
                package="drn_example_inspection",
                executable="heartbeat",
                name="drn_example_inspection",
                output="screen",
                parameters=[{"heartbeat_period": heartbeat_period}],
            ),
        ]
    )
