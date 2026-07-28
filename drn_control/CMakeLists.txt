cmake_minimum_required(VERSION 3.8)
project(drn_control)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(eigen3_cmake_module REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(px4_ros2_cpp REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)

add_executable(drn_control_node src/control_node.cpp)
target_include_directories(drn_control_node PRIVATE include)
ament_target_dependencies(
  drn_control_node
  geometry_msgs
  std_msgs
  std_srvs
)
target_link_libraries(
  drn_control_node
  Eigen3::Eigen
  px4_ros2_cpp::px4_ros2_cpp
  rclcpp::rclcpp
)

install(
  TARGETS drn_control_node
  DESTINATION lib/${PROJECT_NAME}
)
install(
  DIRECTORY include/
  DESTINATION include
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  ament_add_gtest(test_pose_conversion test/test_pose_conversion.cpp)
  target_include_directories(test_pose_conversion PRIVATE include)
  ament_target_dependencies(test_pose_conversion geometry_msgs)
  target_link_libraries(
    test_pose_conversion
    Eigen3::Eigen
    px4_ros2_cpp::px4_ros2_cpp
  )
endif()

ament_package()
