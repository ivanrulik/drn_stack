import os

from ament_index_python.packages import PackageNotFoundError, get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _to_bool(value: str) -> bool:
    return value.lower() in ('1', 'true', 'yes', 'on')


def _launch_setup(context, *args, **kwargs):
    urdf_path = LaunchConfiguration('urdf').perform(context)
    use_joint_state_publisher = _to_bool(LaunchConfiguration('use_joint_state_publisher').perform(context))
    odometry_topic = LaunchConfiguration('odometry_topic').perform(context)
    world_frame = LaunchConfiguration('world_frame').perform(context)
    base_frame = LaunchConfiguration('base_frame').perform(context)

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
        OpaqueFunction(function=_launch_setup),
    ])
