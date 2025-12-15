import requests
from params import get_param
from django.conf import settings

class GearApi:
    def __init__(self):
        self.base_url = get_param("GEAR_API_BASE_URL", "xx")
        self.api_token = get_param("GEAR_API_TOKEN", "xx")
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def get(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        resp = requests.get(url, headers=self.headers, params=params)
        if resp.status_code >= 400:
            raise Exception(f"Erro GET {endpoint}: {resp.status_code} - {resp.text}")
        return resp.json()

    def post(self, endpoint, data=None):
        url = f"{self.base_url}{endpoint}"
        resp = requests.post(url, headers=self.headers, json=data)
        if resp.status_code >= 400:
            raise Exception(f"Erro POST {endpoint}: {resp.status_code} - {resp.text}")
        return resp.json()

    def put(self, endpoint, data=None):
        url = f"{self.base_url}{endpoint}"
        resp = requests.put(url, headers=self.headers, json=data)
        if resp.status_code >= 400:
            raise Exception(f"Erro PUT {endpoint}: {resp.status_code} - {resp.text}")
        return resp.json()

    def delete(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        resp = requests.delete(url, headers=self.headers)
        if resp.status_code >= 400:
            raise Exception(f"Erro DELETE {endpoint}: {resp.status_code} - {resp.text}")
        return resp.json()
