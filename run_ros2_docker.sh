docker run -d --net=host \
           -ti \
           -v $(pwd)/node_manager/ros2_dds_profile.xml:/root/ros2_dds_profile.xml \
           -e DISPLAY=$DISPLAY \
           -v $HOME/.Xauthority:/root/.Xauthority:rw \
           -e FASTRTPS_DEFAULT_PROFILES_FILE=/root/ros2_dds_profile.xml  \
           --privileged \
           --name ros_container \
           -v /tmp/.X11-unix:/tmp/.X11-unix ros_image_subscriber:v1
