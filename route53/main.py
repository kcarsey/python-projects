import urllib.request
import socket
import time
import boto3

sleeptime = 3600

def main(sleeptime):
    try:
        def dns_lookup(hostname):
            try:
                # Resolve the hostname to its IP address
                ip_address = socket.gethostbyname(hostname)
                return ip_address
            except socket.gaierror as e:
                print(f"Error resolving {hostname}: {e}")
                return None
            
        my_ipaddress = urllib.request.urlopen("http://icanhazip.com").read().decode("utf-8").strip("\n")
        dns_ip = dns_lookup("kcnsgp.net")
        
        if dns_ip == my_ipaddress:
            print(f"DNS record matches my ip, sleeping {sleeptime}")
            return
        else:
            print("updating dns record...")
            pass
    except Exception as e:
        print(e)

if __name__ == "__main__":
    main()
    time.sleep(sleeptime)


