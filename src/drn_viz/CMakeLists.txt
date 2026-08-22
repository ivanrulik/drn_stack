cmake_minimum_required(VERSION 3.8)
project(drn_viz)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS aruco calib3d)
find_package(px4_msgs REQUIRED)
find_package(px4_ros_com REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(visualization_msgs REQUIRED)
find_package(Eigen3 REQUIRED)

add_executable(odometry_tf_bridge src/odometry_tf_bridge.cpp)
ament_target_dependencies(odometry_tf_bridge
  geometry_msgs
  px4_msgs
  px4_ros_com
  rclcpp
  tf2_ros
)
target_link_libraries(odometry_tf_bridge Eigen3::Eigen)

add_executable(vision_odometry_adapter src/vision_odometry_adapter.cpp)
ament_target_dependencies(vision_odometry_adapter
  nav_msgs
  rclcpp
)

add_executable(laser_scan_adapter src/laser_scan_adapter.cpp)
ament_target_dependencies(laser_scan_adapter
  rclcpp
  sensor_msgs
)

add_executable(lidar_world_markers src/lidar_world_markers.cpp)
ament_target_dependencies(lidar_world_markers
  rclcpp
  visualization_msgs
)

add_executable(landing_target_detector src/landing_target_detector.cpp)
target_include_directories(landing_target_detector PRIVATE ${OpenCV_INCLUDE_DIRS})
ament_target_dependencies(landing_target_detector
  cv_bridge
  geometry_msgs
  rclcpp
  sensor_msgs
  std_msgs
)
target_link_libraries(landing_target_detector ${OpenCV_LIBS})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

install(TARGETS
  landing_target_detector
  laser_scan_adapter
  lidar_world_markers
  odometry_tf_bridge
  vision_odometry_adapter
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
)

install(DIRECTORY urdf/
  DESTINATION share/${PROJECT_NAME}/urdf
)

install(DIRECTORY meshes/
  DESTINATION share/${PROJECT_NAME}/meshes
)

install(FILES ARK_TRACKTOR_BEAM_LICENSE
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
