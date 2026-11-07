import os
import json
import math
import random
import urllib.request
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


# ==========================================
# AERO - Emergency Route Optimizer
# Backend: Python
# Routing: OSRM (real road routes)
# Traffic: Free simulated traffic
# Deployment: Render compatible
# ==========================================


class AEROHandler(SimpleHTTPRequestHandler):

    # --------------------------------------
    # Send JSON responses
    # --------------------------------------
    def send_json(self, status_code, data):
        body = json.dumps(data).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

    # --------------------------------------
    # Validate GPS coordinates
    # --------------------------------------
    def validate_coordinates(
        self,
        latitude,
        longitude,
        location_name
    ):
        if not math.isfinite(latitude):
            raise ValueError(
                f"{location_name} latitude must be a valid number."
            )

        if not math.isfinite(longitude):
            raise ValueError(
                f"{location_name} longitude must be a valid number."
            )

        if not -90 <= latitude <= 90:
            raise ValueError(
                f"Invalid {location_name.lower()} latitude."
            )

        if not -180 <= longitude <= 180:
            raise ValueError(
                f"Invalid {location_name.lower()} longitude."
            )

    # --------------------------------------
    # Request real road route from OSRM
    # --------------------------------------
    def get_road_route(
        self,
        start_lat,
        start_lon,
        end_lat,
        end_lon
    ):
        coordinates = (
            f"{start_lon},{start_lat};"
            f"{end_lon},{end_lat}"
        )

        url = (
            "https://router.project-osrm.org/route/v1/driving/"
            + coordinates
            + "?overview=full&geometries=geojson"
        )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AERO-EmergencyRouteOptimizer/1.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=25
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

        if data.get("code") != "Ok":
            raise ValueError(
                "OSRM could not find a road route for these locations."
            )

        routes = data.get("routes", [])

        if not routes:
            raise ValueError(
                "No road route found. Try different locations."
            )

        return routes[0]

    # --------------------------------------
    # Free simulated traffic
    # NOTE: This is not live traffic data.
    # --------------------------------------
    def simulate_traffic(self, duration_seconds):
        traffic_levels = [
            {
                "level": "Low",
                "multiplier": 1.0,
                "description": "Light simulated traffic"
            },
            {
                "level": "Moderate",
                "multiplier": 1.2,
                "description": "Moderate simulated traffic"
            },
            {
                "level": "High",
                "multiplier": 1.5,
                "description": "Heavy simulated traffic"
            }
        ]

        traffic = random.choices(
            traffic_levels,
            weights=[50, 35, 15],
            k=1
        )[0]

        estimated_seconds = (
            duration_seconds * traffic["multiplier"]
        )

        return {
            "traffic_level": traffic["level"],
            "traffic_description": traffic["description"],
            "traffic_multiplier": traffic["multiplier"],
            "base_duration_min": round(
                duration_seconds / 60, 1
            ),
            "estimated_duration_min": round(
                estimated_seconds / 60, 1
            ),
            "traffic_type": "simulated",
            "is_live_traffic": False
        }

    # --------------------------------------
    # GET requests
    # --------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # Health check for hosting platforms
        if parsed.path == "/health":
            self.send_json(200, {
                "status": "ok",
                "application": "AERO",
                "message": "AERO server is running."
            })
            return

        # Route endpoint
        if parsed.path == "/route":
            params = urllib.parse.parse_qs(
                parsed.query
            )

            try:
                # Read coordinates
                start_lat = float(
                    params["start_lat"][0]
                )
                start_lon = float(
                    params["start_lon"][0]
                )
                end_lat = float(
                    params["end_lat"][0]
                )
                end_lon = float(
                    params["end_lon"][0]
                )

                # Validate GPS coordinates
                self.validate_coordinates(
                    start_lat,
                    start_lon,
                    "Starting location"
                )

                self.validate_coordinates(
                    end_lat,
                    end_lon,
                    "Destination"
                )

                # Get real road route
                route = self.get_road_route(
                    start_lat,
                    start_lon,
                    end_lat,
                    end_lon
                )

                distance_m = float(
                    route["distance"]
                )
                duration_seconds = float(
                    route["duration"]
                )

                # Simulate traffic
                traffic = self.simulate_traffic(
                    duration_seconds
                )

                # Send route details to frontend
                result = {
                    "success": True,
                    "distance_km": round(
                        distance_m / 1000, 2
                    ),
                    "distance_m": round(distance_m),
                    "duration_min": round(
                        duration_seconds / 60, 1
                    ),
                    "duration_seconds": round(
                        duration_seconds
                    ),
                    "geometry": route["geometry"],
                    "traffic": traffic
                }

                self.send_json(200, result)

            except KeyError:
                self.send_json(400, {
                    "success": False,
                    "error": (
                        "Missing coordinates. Provide start_lat, "
                        "start_lon, end_lat and end_lon."
                    )
                })

            except (ValueError, TypeError) as error:
                self.send_json(400, {
                    "success": False,
                    "error": str(error)
                })

            except Exception as error:
                print("AERO routing error:", error)

                self.send_json(502, {
                    "success": False,
                    "error": (
                        "Routing service is temporarily unavailable. "
                        "Check your internet connection and try again."
                    )
                })

            return

        # Open index.html for the homepage
        if parsed.path == "/":
            self.path = "/index.html"

        return super().do_GET()

    # --------------------------------------
    # Server logging
    # --------------------------------------
    def log_message(self, format_string, *args):
        print(
            f"{self.client_address[0]} - "
            f"{format_string % args}"
        )


# ==========================================
# Start AERO server
# ==========================================
if __name__ == "__main__":

    # Render supplies PORT automatically.
    # Local development uses port 8000.
    port = int(
        os.environ.get("PORT", "8000")
    )

    server = ThreadingHTTPServer(
        ("0.0.0.0", port),
        AEROHandler
    )

    print(
        f"AERO Emergency Route Optimizer running on port {port}"
    )
    print("Press Ctrl+C to stop the server.")

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print("\nStopping AERO server...")

    finally:
        server.server_close()
