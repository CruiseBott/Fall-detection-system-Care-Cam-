// WebSocket connection for real-time fall detection alerts
class FallDetectionSocket {
  constructor(userId) {
    this.userId = userId;
    this.socket = null;
    this.connected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 3000; // 3 seconds
  }

  connect() {
    // Use secure WebSocket if the page is served over HTTPS
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/fall_detection/${this.userId}`;

    this.socket = new WebSocket(wsUrl);

    this.socket.onopen = () => {
      console.log('WebSocket connection established');
      this.connected = true;
      this.reconnectAttempts = 0;
    };

    this.socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };

    this.socket.onclose = (event) => {
      console.log('WebSocket connection closed', event);
      this.connected = false;
      this.attemptReconnect();
    };

    this.socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  handleMessage(data) {
    if (data.type === 'fall_detection') {
      // Show fall detection alert
      document.getElementById('detection-status').style.display = 'none';
      document.getElementById('alert-info').style.display = 'block';
      document.getElementById('detection-time').textContent = new Date(data.timestamp).toLocaleString();
      document.getElementById('detection-location').textContent = data.location || 'Unknown';
      
      // Play alert sound if available
      const alertSound = document.getElementById('alert-sound');
      if (alertSound) {
        alertSound.play();
      }
      
      // Show notification if browser supports it
      if ('Notification' in window) {
        if (Notification.permission === 'granted') {
          new Notification('Fall Detected!', {
            body: `A fall was detected at ${new Date(data.timestamp).toLocaleString()}`,
            icon: '/static/img/alert-icon.png'
          });
        } else if (Notification.permission !== 'denied') {
          Notification.requestPermission();
        }
      }
    }
  }

  attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
      
      setTimeout(() => {
        this.connect();
      }, this.reconnectDelay);
    } else {
      console.error('Maximum reconnection attempts reached. Please refresh the page.');
    }
  }

  sendMessage(message) {
    if (this.connected) {
      this.socket.send(JSON.stringify(message));
    } else {
      console.error('Cannot send message: WebSocket is not connected');
    }
  }

  close() {
    if (this.socket) {
      this.socket.close();
    }
  }
}

// Initialize WebSocket connection when the page loads
document.addEventListener('DOMContentLoaded', function() {
  const userId = document.getElementById('user-id')?.value;
  
  if (userId) {
    const fallDetectionSocket = new FallDetectionSocket(userId);
    fallDetectionSocket.connect();
    
    // Store the socket instance in window for global access
    window.fallDetectionSocket = fallDetectionSocket;
    
    // Clean up when the page is unloaded
    window.addEventListener('beforeunload', () => {
      fallDetectionSocket.close();
    });
  }
});