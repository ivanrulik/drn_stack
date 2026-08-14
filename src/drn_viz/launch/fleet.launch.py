"""Launch an inert, observation-only two-vehicle PX4 visualization."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


VEHICLES = (
    ('px4_1', '0', '0', '/px4_1/fmu/out/vehicle_odometry'),
    ('px4_2', '0', '2', '/px4_2/fmu/out/vehicle_odometry'),
)


def _launch_setup(context, *args, **kwargs):
    """Create isolated telemetry consumers without loading flight control."""
    del args, kwargs
    urdf_path = LaunchConfiguration('urdf').perform(context)
    foxglove_port = int(LaunchConfiguration('foxglove_port').perform(context))

    with open(urdf_path, 'r', encoding='utf-8') as urdf_file:
        robot_description = urdf_file.read()

    nodes = [
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
    ]

    for namespace, spawn_x, spawn_y, odometry_topic in VEHICLES:
        local_map = f'{namespace}/map'
        base_frame = f'{namespace}/base_link'
        nodes.extend([
            Node(
                package='tf2_ros',
                executable='static_transform_publisher',
                namespace=namespace,
                name='map_origin',
                output='screen',
                arguments=[
                    '--x', spawn_x,
                    '--y', spawn_y,
                    '--z', '0',
                    '--roll', '0',
                    '--pitch', '0',
                    '--yaw', '0',
                    '--frame-id', 'map',
                    '--child-frame-id', local_map,
                ],
            ),
            Node(
                package='robot_state_publisher',
                executable='robot_state_publisher',
                namespace=namespace,
                name='robot_state_publisher',
                output='screen',
                parameters=[{
                    'robot_description': robot_description,
                    'frame_prefix': f'{namespace}/',
                }],
            ),
            Node(
                package='drn_viz',
                executable='odometry_tf_bridge',
                namespace=namespace,
                name='odometry_tf_bridge',
                output='screen',
                parameters=[{
                    'odometry_topic': odometry_topic,
                    'world_frame': local_map,
                    'base_frame': base_frame,
                }],
            ),
        ])

    return nodes


def generate_launch_description():
    """Declare the fixed two-vehicle observation surface."""
    package_share = get_package_share_directory('drn_viz')
    default_urdf_path = os.path.join(package_share, 'urdf', 'x500.urdf')
    return LaunchDescription([
        DeclareLaunchArgument('urdf', default_value=default_urdf_path),
        DeclareLaunchArgument('foxglove_port', default_value='8765'),
        OpaqueFunction(function=_launch_setup),
    ])
