import math


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def decode_polyline6(encoded: str):
    """Decode a Valhalla polyline (precision 6) into [[lng, lat], ...]."""
    coords, index, lat, lng = [], 0, 0, 0
    while index < len(encoded):
        for is_lng in (False, True):
            shift, result = 0, 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lng:
                lng += delta
            else:
                lat += delta
        coords.append([lng / 1e6, lat / 1e6])
    return coords


def cluster(points, radius_km=0.1):
    """Greedy clustering: returns a cluster index per point (same index = same place)."""
    centers, labels = [], []
    for lat, lng in points:
        for i, (clat, clng) in enumerate(centers):
            if haversine_km(lat, lng, clat, clng) <= radius_km:
                labels.append(i)
                break
        else:
            centers.append((lat, lng))
            labels.append(len(centers) - 1)
    return labels
