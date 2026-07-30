"""Launch the DRN x500 visualization and PX4 odometry bridge."""

import os

from ament_index_python.packages import (
    get_package_prefix,
    get_package_share_directory,
    PackageNotFoundError,
)
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _to_bool(value: str) -> bool:
    """Convert a launch argument string to a boolean."""
    return value.lower() in ('1', 'true', 'yes', 'on')


def _launch_setup(context, *args, **kwargs):
    """Create nodes after launch arguments have been resolved."""
    urdf_path = LaunchConfiguration('urdf').perform(context)
    use_joint_state_publisher = _to_bool(
        LaunchConfiguration('use_joint_state_publisher').perform(context)
    )
    odometry_topic = LaunchConfiguration('odometry_topic').perform(context)
    world_frame = LaunchConfiguration('world_frame').perform(context)
    base_frame = LaunchConfiguration('base_frame').perform(context)
    foxglove_port = int(LaunchConfiguration('foxglove_port').perform(context))

    with open(urdf_path, 'r', encoding='utf-8') as urdf_file:
        robot_description = urdf_file.read()

    nodes = [
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
            parameters=[
                {
                    'address': '0.0.0.0',
                    'port': foxglove_port,
                    'client_topic_whitelist': [
                        r'^/drn/control/setpoint$',
                        r'^/drn/control/teleop/xy$',
                        r'^/drn/control/teleop/z_yaw$',
                    ],
                    'service_whitelist': [
                        r'^/drn/control/(activate|takeoff|hold|land|rtl)$',
                    ],
                }
            ],
        ),
        Node(
            package='drn_viz',
            executable='odometry_tf_bridge',
            name='odometry_tf_bridge',
            output='screen',
            parameters=[
                {
                    'odometry_topic': odometry_topic,
                    'world_frame': world_frame,
                    'base_frame': base_frame,
                }
            ],
        ),
        Node(
            package='drn_control',
            executable='drn_control_node',
            name='drn_control',
            output='screen',
            respawn=True,
            respawn_delay=2.0,
        ),
    ]

    if use_joint_state_publisher:
        try:
            get_package_prefix('joint_state_publisher')
            nodes.append(
                Node(
                    package='joint_state_publisher',
                    executable='joint_state_publisher',
                    name='joint_state_publisher',
                    output='screen',
                )
            )
        except PackageNotFoundError:
            nodes.append(
                LogInfo(msg='joint_state_publisher was requested but is not installed. Skipping.')
            )

    return nodes


def generate_launch_description():
    """Declare launch arguments and defer node construction."""
    package_share = get_package_share_directory('drn_viz')
    default_urdf_path = os.path.join(package_share, 'urdf', 'x500.urdf')

    return LaunchDescription([
        DeclareLaunchArgument(
            'urdf',
            default_value=default_urdf_path,
            description='Absolute path to the x500 URDF file.',
        ),
        DeclareLaunchArgument(
            'use_joint_state_publisher',
            default_value='false',
            description='Start joint_state_publisher alongside robot_state_publisher.',
        ),
        DeclareLaunchArgument(
            'odometry_topic',
            default_value='/fmu/out/vehicle_odometry',
            description='PX4 odometry topic used to publish map->base_link TF.',
        ),
        DeclareLaunchArgument(
            'world_frame',
            default_value='map',
            description='Parent TF frame for the drone pose.',
        ),
        DeclareLaunchArgument(
            'base_frame',
            default_value='base_link',
            description='Drone base TF frame name.',
        ),
        DeclareLaunchArgument(
            'foxglove_port',
            default_value='8765',
            description='TCP port for Foxglove Bridge.',
        ),
        OpaqueFunction(function=_launch_setup),
    ])
