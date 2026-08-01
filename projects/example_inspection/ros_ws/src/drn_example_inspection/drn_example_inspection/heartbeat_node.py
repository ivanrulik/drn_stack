"""Publish an inert heartbeat for project health validation."""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class InspectionHeartbeat(Node):
    """Emit a bounded-rate status message without commanding the vehicle."""

    def __init__(self) -> None:
        super().__init__("drn_example_inspection")
        self.declare_parameter("heartbeat_period", 1.0)
        period = self.get_parameter("heartbeat_period").get_parameter_value().double_value
        if period <= 0.0:
            raise ValueError("heartbeat_period must be positive")
        self.publisher = self.create_publisher(
            String, "/drn/example_inspection/heartbeat", 1
        )
        self.timer = self.create_timer(period, self.publish_heartbeat)

    def publish_heartbeat(self) -> None:
        """Publish a deterministic health message."""
        message = String()
        message.data = "ready"
        self.publisher.publish(message)


def main(args=None) -> None:
    """Run the example node."""
    rclpy.init(args=args)
    node = InspectionHeartbeat()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
