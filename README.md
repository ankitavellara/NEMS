# **NEMS - Network Event Monitoring System**

NEMS is a UDP-based Network Event Monitoring System that collects system metrics such as CPU usage, memory usage, latency and temperature from 
multiple client nodes. The server receives packets, verifies them using HMAC-SHA256 authentication, classifies events into INFO/WARNING/CRITICAL, 
and displays them on a live dashboard. The system also supports performance evaluation using a load-test client.

## **FEATURES**

- UDP-based multi-client monitoring
- HMAC-SHA256 authenticated packets
- Real-time event classification: INFO, WARNING, CRITICAL
- Packet loss tracking using sequence numbers
- Live React dashboard
- Node online/offline detection
- Performance metrics: packets/sec, delay, rejected packets
- Load testing support for performance evaluation

## **PROJECT STRUCTURE**
- `server.py` - UDP server + dashboard API
- `client.py` - Normal monitoring client
- `load_test_client.py` - Simulated multi-node performance test client
- `dashboard/` - Frontend files for live dashboard
- `events.log` - Server event log output

## **REQUIREMENTS**
- Python 3.10+
- Windows 10/11
- `psutil` Python package

## **SETUP**
1. Clone or download the project.
2. Open PowerShell in the project folder.
3. Install dependencies:

```powershell
pip install psutil
```
If Python is not recognized in PowerShell, install Python from python.org and ensure it is added to PATH.

## **USAGE**

### 1. Start the Server

Run on the main machine:

```powershell
python server.py
```

This starts:

UDP server on port 5000
Dashboard on port 8000

### 2. Open the Dashboard

In a browser, open:
http://localhost:8000

### 3. Run a Normal Client
On the same machine or another laptop in the same network, edit client.py:

SERVER_HOST = "YOUR_SERVER_IP"
NODE_NAME = "PC_1"
Then run:

```python client.py```

### 4. Run Multiple Real Clients
For each client laptop:

1. connect to the same Wi-Fi/LAN
2. set a unique NODE_NAME
3. set SERVER_HOST to the server laptop's IPv4 address
4. run python client.py

### 5. Run Performance Testing
To simulate multiple nodes from one machine:

```python load_test_client.py --server-host YOUR_SERVER_IP --nodes 5 --interval 1 --duration 30 --mode mixed```

### 6. Firewall Note

If clients on other laptops cannot reach the server, allow UDP port `5000` through Windows Firewall:

```New-NetFirewallRule -DisplayName "NEMS UDP 5000" -Direction Inbound -Protocol UDP -LocalPort 5000 -Action Allow```

### 7. Performance Evaluation Section

**Performance Evaluation**
The system was evaluated using:
- multiple concurrent clients
- the `load_test_client.py` script
- varying packet rates and node counts

Metrics observed:
- packets per second
- average delay
- maximum delay
- packet loss percentage
- rejected packets
- online/offline node tracking
  
### 8. Security Note

**Security**
The system uses HMAC-SHA256 to authenticate UDP packets and prevent tampering.
Timestamp validation is used to reject stale or replayed packets.




