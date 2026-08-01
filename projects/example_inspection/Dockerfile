FROM drn-stack/ros-viz:humble AS project-builder

WORKDIR /opt/drn_project_ws
COPY ros_ws/src/ src/
RUN . /opt/drn_ws/install/setup.sh \
    && colcon build \
        --merge-install \
        --packages-select drn_example_inspection

FROM drn-stack/ros-viz:humble

COPY --from=project-builder /opt/drn_project_ws/install/ /opt/drn_project_ws/install/
ENV DRN_PROJECT_SETUP=/opt/drn_project_ws/install/setup.bash
