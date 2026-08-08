"""Launch the DRN x500 visualization and PX4 odometry bridge."""

import os
import re

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
    profile = LaunchConfiguration('profile').perform(context)
    airframe = LaunchConfiguration('airframe').perform(context)
    capabilities = {
        capability
        for capability in LaunchConfiguration('capabilities').perform(context).split(',')
        if capability
    }
    model_name = LaunchConfiguration('model_name').perform(context)
    world_name = LaunchConfiguration('world_name').perform(context)

    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', profile):
        raise RuntimeError(f"Invalid DRN profile name: {profile}")
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', airframe):
        raise RuntimeError(f"Invalid DRN airframe name: {airframe}")
    supported_capabilities = {'depth-camera', 'vision-odometry'}
    unknown_capabilities = capabilities - supported_capabilities
    if unknown_capabilities:
        raise RuntimeError(
            f"Unsupported DRN profile capabilities: {sorted(unknown_capabilities)}"
        )
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', model_name):
        raise RuntimeError(f"Invalid Gazebo model name: {model_name}")

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

    if 'depth-camera' in capabilities:
        color_gz_topic = (
            f'/world/{world_name}/model/{model_name}/link/camera_link/'
            'sensor/IMX214/image'
        )
        color_info_gz_topic = (
            f'/world/{world_name}/model/x500_depth_0/link/camera_link/'
            'sensor/IMX214/camera_info'
        )
        depth_gz_topic = '/depth_camera'
        depth_info_gz_topic = '/camera_info'
        nodes.extend([
            Node(
                package='ros_gz_bridge',
                executable='parameter_bridge',
                name='depth_camera_bridge',
                output='screen',
                arguments=[
                    f'{color_gz_topic}@sensor_msgs/msg/Image[gz.msgs.Image',
                    (
                        f'{color_info_gz_topic}@sensor_msgs/msg/CameraInfo'
                        '[gz.msgs.CameraInfo'
                    ),
                    f'{depth_gz_topic}@sensor_msgs/msg/Image[gz.msgs.Image',
                    (
                        f'{depth_info_gz_topic}@sensor_msgs/msg/CameraInfo'
                        '[gz.msgs.CameraInfo'
                    ),
                ],
                remappings=[
                    (color_gz_topic, '/drn/sensors/front/color/image_raw'),
                    (color_info_gz_topic, '/drn/sensors/front/color/camera_info'),
                    (depth_gz_topic, '/drn/sensors/front/depth/image_raw'),
                    (depth_info_gz_topic, '/drn/sensors/front/depth/camera_info'),
                ],
            ),
            Node(
                package='tf2_ros',
                executable='static_transform_publisher',
                name='depth_camera_tf',
                output='screen',
                arguments=[
                    '--x', '0.13233', '--y', '0', '--z', '0.26078',
                    '--roll', '-1.57079632679',
                    '--pitch', '0',
                    '--yaw', '-1.57079632679',
                    '--frame-id', base_frame,
                    '--child-frame-id', 'camera_link',
                ],
            ),
        ])

    if 'vision-odometry' in capabilities:
        vision_gz_topic = f'/model/{model_name}/odometry_with_covariance'
        raw_vision_topic = '/drn/internal/vision/odometry'
        nodes.extend([
            Node(
                package='ros_gz_bridge',
                executable='parameter_bridge',
                name='vision_odometry_bridge',
                output='screen',
                arguments=[
                    f'{vision_gz_topic}@nav_msgs/msg/Odometry'
                    '[gz.msgs.OdometryWithCovariance',
                ],
                remappings=[
                    (vision_gz_topic, raw_vision_topic),
                ],
            ),
            Node(
                package='drn_viz',
                executable='vision_odometry_adapter',
                name='vision_odometry_adapter',
                output='screen',
                parameters=[{
                    'input_topic': raw_vision_topic,
                    'output_topic': '/drn/sensors/vision/odometry',
                    'world_frame': world_frame,
                    'base_frame': base_frame,
                }],
            ),
        ])

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
        DeclareLaunchArgument(
            'profile',
            default_value='x500-basic',
            description='Selected profile directory name.',
        ),
        DeclareLaunchArgument(
            'airframe',
            default_value='x500',
            description='Airframe family declared by the selected profile.',
        ),
        DeclareLaunchArgument(
            'capabilities',
            default_value='',
            description='Comma-separated profile capabilities.',
        ),
        DeclareLaunchArgument(
            'model_name',
            default_value='x500_0',
            description='Spawned Gazebo model instance name.',
        ),
        DeclareLaunchArgument(
            'world_name',
            default_value='default',
            description='Gazebo world name used to resolve sensor topics.',
        ),
        OpaqueFunction(function=_launch_setup),
    ])
