"""Launch an inert, observation-only bounded PX4 fleet visualization."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


MIN_FLEET_SIZE = 2
MAX_FLEET_SIZE = 4


def _fleet_specs(size):
    """Return deterministic namespaces, grid poses, and odometry topics."""
    specs = []
    for instance in range(1, size + 1):
        spawn_index = instance - 1
        spawn_x = (spawn_index // 2) * 2
        spawn_y = (spawn_index % 2) * 2
        namespace = f'px4_{instance}'
        specs.append((
            namespace,
            str(spawn_x),
            str(spawn_y),
            f'/{namespace}/fmu/out/vehicle_odometry',
        ))
    return tuple(specs)


def _launch_setup(context, *args, **kwargs):
    """Create isolated telemetry consumers without loading flight control."""
    del args, kwargs
    urdf_path = LaunchConfiguration('urdf').perform(context)
    foxglove_port = int(LaunchConfiguration('foxglove_port').perform(context))
    fleet_size_text = LaunchConfiguration('fleet_size').perform(context)
    try:
        fleet_size = int(fleet_size_text)
    except ValueError as error:
        raise ValueError('fleet_size must be an integer from 2 through 4') from error
    if not MIN_FLEET_SIZE <= fleet_size <= MAX_FLEET_SIZE:
        raise ValueError('fleet_size must be an integer from 2 through 4')

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

    for namespace, spawn_x, spawn_y, odometry_topic in _fleet_specs(fleet_size):
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
    """Declare the bounded fleet observation surface."""
    package_share = get_package_share_directory('drn_viz')
    default_urdf_path = os.path.join(package_share, 'urdf', 'x500.urdf')
    return LaunchDescription([
        DeclareLaunchArgument('urdf', default_value=default_urdf_path),
        DeclareLaunchArgument(
            'fleet_size', default_value=os.environ.get('DRN_FLEET_SIZE', '2')
        ),
        DeclareLaunchArgument('foxglove_port', default_value='8765'),
        OpaqueFunction(function=_launch_setup),
    ])
