"""Launch a read-only Foxglove bridge for evidence-pack replay."""

from launch import LaunchDescription
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch.actions import DeclareLaunchArgument


def generate_launch_description():
    """Expose replayed ROS topics without any control publication or services."""
    return LaunchDescription([
        DeclareLaunchArgument(
            'foxglove_port',
            default_value='8765',
            description='TCP port for the replay-only Foxglove Bridge.',
        ),
        Node(
            package='foxglove_bridge',
            executable='foxglove_bridge',
            name='foxglove_replay_bridge',
            output='screen',
            parameters=[{
                'address': '0.0.0.0',
                'port': ParameterValue(
                    LaunchConfiguration('foxglove_port'), value_type=int
                ),
                'client_topic_whitelist': [r'^$'],
                'service_whitelist': [r'^$'],
            }],
        ),
    ])
