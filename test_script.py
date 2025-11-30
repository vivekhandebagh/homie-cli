import socket
import platform
import os

print("Hello from a homie's machine!")
print(f"Hostname: {socket.gethostname()}")
print(f"Platform: {platform.system()} {platform.release()}")
print(f"Python: {platform.python_version()}")
print(f"CPU cores: {os.cpu_count()}")
print()
print("If you see this, homie compute is working!")
