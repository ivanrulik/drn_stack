cmake_minimum_required(VERSION 3.8)
project(drn_viz)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(px4_msgs REQUIRED)
find_package(px4_ros_com REQUIRED)
find_package(rclcpp REQUIRED)
find_package(tf2_ros REQUIRED)
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

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

install(TARGETS
  odometry_tf_bridge
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

ament_package()
