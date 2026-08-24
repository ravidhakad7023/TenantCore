import uuid
import random
from locust import HttpUser, task, between, events

class SaaSUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.org_id = None
        self.project_id = None
        self.headers = {}
        self.task_ids = []
        self.report_ids = []
        
        # Generate random user credentials
        self.email = f"user_{uuid.uuid4()}@example.com"
        self.password = "password123"
        
        # 1. Register
        self.client.post("/api/v1/auth/register", json={"email": self.email, "password": self.password})
        
        # 2. Login
        login_resp = self.client.post("/api/v1/auth/login", json={"email": self.email, "password": self.password})
        if login_resp.status_code == 200:
            self.token = login_resp.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}
            return
            
        # 3. Create an organization
        org_resp = self.client.post("/api/v1/organizations", json={"name": f"Org {uuid.uuid4().hex[:8]}"}, headers=self.headers)
        if org_resp.status_code in (200, 201):
            self.org_id = org_resp.json()["id"]
        else:
            self.org_id = None
            return
            
        # 4. Create a project
        proj_resp = self.client.post(f"/api/v1/organizations/{self.org_id}/projects", json={"name": "Load Test Project"}, headers=self.headers)
        if proj_resp.status_code in (200, 201):
            self.project_id = proj_resp.json()["id"]
        else:
            self.project_id = None
            return

        # Create initial tasks
        for i in range(5):
            self.create_task()

    def create_task(self):
        if not self.project_id:
            return
        resp = self.client.post(
            f"/api/v1/organizations/{self.org_id}/projects/{self.project_id}/tasks",
            json={
                "title": f"Task {uuid.uuid4().hex[:8]}",
                "status": random.choice(["TODO", "IN_PROGRESS", "DONE"]),
                "priority": random.choice(["LOW", "MEDIUM", "HIGH"])
            },
            headers=self.headers,
            name="/api/v1/organizations/{org_id}/projects/{project_id}/tasks"
        )
        if resp.status_code in (200, 201):
            self.task_ids.append(resp.json()["id"])

    @task(3)
    def get_organizations(self):
        self.client.get("/api/v1/organizations", headers=self.headers, name="/api/v1/organizations")

    @task(3)
    def get_organization(self):
        if self.org_id:
            self.client.get(f"/api/v1/organizations/{self.org_id}", headers=self.headers, name="/api/v1/organizations/{org_id}")

    @task(3)
    def list_projects(self):
        if self.org_id:
            self.client.get(f"/api/v1/organizations/{self.org_id}/projects", headers=self.headers, name="/api/v1/organizations/{org_id}/projects")

    @task(3)
    def get_project(self):
        if self.org_id and self.project_id:
            self.client.get(f"/api/v1/organizations/{self.org_id}/projects/{self.project_id}", headers=self.headers, name="/api/v1/organizations/{org_id}/projects/{project_id}")

    @task(5)
    def list_tasks(self):
        if self.org_id and self.project_id:
            self.client.get(f"/api/v1/organizations/{self.org_id}/projects/{self.project_id}/tasks", headers=self.headers, name="/api/v1/organizations/{org_id}/projects/{project_id}/tasks")

    @task(4)
    def filter_tasks_status(self):
        if self.org_id and self.project_id:
            status = random.choice(["TODO", "IN_PROGRESS", "DONE"])
            self.client.get(f"/api/v1/organizations/{self.org_id}/projects/{self.project_id}/tasks?status={status}", headers=self.headers, name="/api/v1/organizations/{org_id}/projects/{project_id}/tasks?status=[status]")

    @task(2)
    def create_new_task(self):
        self.create_task()

    @task(4)
    def get_task(self):
        if self.org_id and self.project_id and self.task_ids:
            task_id = random.choice(self.task_ids)
            self.client.get(f"/api/v1/organizations/{self.org_id}/projects/{self.project_id}/tasks/{task_id}", headers=self.headers, name="/api/v1/organizations/{org_id}/projects/{project_id}/tasks/{task_id}")

    @task(1)
    def create_report(self):
        if self.org_id:
            resp = self.client.post(f"/api/v1/organizations/{self.org_id}/reports", headers=self.headers, name="/api/v1/organizations/{org_id}/reports")
            if resp.status_code in (200, 201, 202):
                self.report_ids.append(resp.json()["id"])

    @task(2)
    def poll_report(self):
        if self.org_id and self.report_ids:
            report_id = random.choice(self.report_ids)
            self.client.get(f"/api/v1/organizations/{self.org_id}/reports/{report_id}", headers=self.headers, name="/api/v1/organizations/{org_id}/reports/{report_id}")
