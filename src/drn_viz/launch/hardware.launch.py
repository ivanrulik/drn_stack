"""Launch the inert, read-only visualization path for PX4 bench hardware."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_setup(context, *args, **kwargs):
    """Create only telemetry consumers; never load the flight-control node."""
    del args, kwargs
    urdf_path = LaunchConfiguration('urdf').perform(context)
    odometry_topic = LaunchConfiguration('odometry_topic').perform(context)
    foxglove_port = int(LaunchConfiguration('foxglove_port').perform(context))

    with open(urdf_path, 'r', encoding='utf-8') as urdf_file:
        robot_description = urdf_file.read()

    return [
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_description}],
        ),
        Node(
            package='foxglove_bridge',
            executable='foxglove_bridge',
            name='foxglove_bridge',
            output='screen',
            parameters=[{
                'address': '0.0.0.0',
                'port': foxglove_port,
                'client_topic_whitelist': [r'^$'],
                'service_whitelist': [r'^$'],
            }],
        ),
        Node(
            package='drn_viz',
            executable='odometry_tf_bridge',
            name='odometry_tf_bridge',
            output='screen',
            parameters=[{'odometry_topic': odometry_topic}],
        ),
    ]


def generate_launch_description():
    """Declare the small set of arguments allowed by hardware mode."""
    package_share = get_package_share_directory('drn_viz')
    default_urdf_path = os.path.join(package_share, 'urdf', 'x500.urdf')
    return LaunchDescription([
        DeclareLaunchArgument('urdf', default_value=default_urdf_path),
        DeclareLaunchArgument(
            'odometry_topic', default_value='/fmu/out/vehicle_odometry'
        ),
        DeclareLaunchArgument('foxglove_port', default_value='8765'),
        OpaqueFunction(function=_launch_setup),
    ])
