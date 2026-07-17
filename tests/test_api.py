"""
ReqWeaver Unit Tests
=====================
Covers: API CRUD, background document generation, validation, security headers, AI status.
"""
from __future__ import annotations
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from app.main import app
from app.database import engine


@pytest.fixture(autouse=True)
def setup_db():
    """Create fresh tables before each test."""
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── Health ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"


# ─── Security Headers ──────────────────────────────────

@pytest.mark.asyncio
async def test_security_headers(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("x-xss-protection") == "1; mode=block"
    assert "strict-transport-security" in resp.headers


# ─── CRUD ───────────────────────────────────────────────

SAMPLE_PROJECT = {
    "name": "Sistem Inventaris",
    "description": "Sistem manajemen inventaris gudang",
    "goals": "Digitalisasi stok\nTracking real-time\nLaporan otomatis",
    "tech_stack": "React + FastAPI + PostgreSQL",
    "stakeholders": [
        {"name": "Budi", "role": "Warehouse Manager", "influence": "high", "interest": "high"},
        {"name": "Ani", "role": "Finance", "influence": "medium", "interest": "low"},
    ],
    "target_users": [
        {"persona_name": "Staff Gudang", "description": "Input barang keluar/masuk", "pain_points": "Sering salah catat"},
    ],
    "features": [
        {"name": "Manajemen Stok", "description": "CRUD barang + stok", "priority": "must"},
        {"name": "Laporan", "description": "Generate laporan periodik", "priority": "should"},
    ],
    "functional_reqs": [
        {"req_id": "FR-001", "title": "Login", "description": "User dapat login dengan email & password", "category": "auth", "priority": "critical"},
        {"req_id": "FR-002", "title": "CRUD Barang", "description": "Admin dapat menambah, mengubah, menghapus barang", "category": "data", "priority": "high"},
    ],
    "non_functional_reqs": [
        {"category": "performance", "description": "Halaman harus loading <2 detik", "metric": "<2000ms", "priority": "high"},
        {"category": "security", "description": "Semua password harus di-hash bcrypt", "metric": "bcrypt", "priority": "critical"},
    ],
    "entities": [
        {
            "name": "User",
            "description": "Pengguna sistem",
            "attributes": [
                {"name": "id", "type": "uuid", "is_pk": True, "nullable": False},
                {"name": "email", "type": "string", "is_pk": False, "nullable": False},
                {"name": "name", "type": "string", "nullable": True},
            ]
        },
        {
            "name": "Product",
            "description": "Barang di gudang",
            "attributes": [
                {"name": "id", "type": "uuid", "is_pk": True, "nullable": False},
                {"name": "name", "type": "string", "nullable": False},
                {"name": "stock", "type": "integer", "nullable": False},
            ]
        }
    ],
    "relationships": [
        {"source_entity": "User", "target_entity": "Product", "relationship_type": "one-to-many", "description": "User manages products"},
    ],
    "sequence_flows": [
        {
            "title": "Login Flow",
            "actors": "User, System, Database",
            "steps": "User -> System: Login Request\nSystem -> Database: Validate Credentials\nDatabase -->> System: Success\nSystem -->> User: JWT Token",
        }
    ],
}


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient):
    resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Sistem Inventaris"
    assert len(data["stakeholders"]) == 2
    assert len(data["features"]) == 2
    assert len(data["functional_reqs"]) == 2
    assert len(data["entities"]) == 2
    assert len(data["relationships"]) == 1
    assert len(data["sequence_flows"]) == 1
    assert "id" in data


@pytest.mark.asyncio
async def test_create_project_validation_error(client: AsyncClient):
    """Empty name should fail."""
    resp = await client.post("/api/projects", json={"name": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient):
    # Empty list
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json() == []

    # With one project
    await client.post("/api/projects", json=SAMPLE_PROJECT)
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Sistem Inventaris"
    assert "stats" in data[0]
    assert "generation_versions" in data[0]


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    resp = await client.get(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Sistem Inventaris"


@pytest.mark.asyncio
async def test_get_project_404(client: AsyncClient):
    resp = await client.get("/api/projects/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    resp = await client.patch(f"/api/projects/{pid}", json={"name": "Sistem Inventaris V2"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Sistem Inventaris V2"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/projects/{pid}")
    assert resp.status_code == 404


# ─── Background Document Generation ────────────────────

@pytest.mark.asyncio
async def test_trigger_background_generation(client: AsyncClient):
    """Trigger background generation and verify it completes."""
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    # Trigger single doc (synchronous in test since no BackgroundTasks)
    resp = await client.post(f"/api/projects/{pid}/generate/prd?mode=template")
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_type"] == "prd"
    assert data["status"] == "pending"
    assert "generation_id" in data
    assert data["version"] == 1

    gen_id = data["generation_id"]

    # Poll status until complete
    import time
    for _ in range(10):
        resp = await client.get(f"/api/projects/{pid}/generations/{gen_id}/status")
        assert resp.status_code == 200
        status = resp.json()["status"]
        if status == "completed":
            break
        time.sleep(0.1)

    # Verify content exists
    resp = await client.get(f"/api/projects/{pid}/generations/{gen_id}")
    assert resp.status_code == 200
    gen_data = resp.json()
    assert gen_data["status"] == "completed"
    assert len(gen_data["content"]) > 0
    assert "Sistem Inventaris" in gen_data["content"]


@pytest.mark.asyncio
async def test_generation_version_increment(client: AsyncClient):
    """Each generation gets a new version number."""
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    # First gen
    resp = await client.post(f"/api/projects/{pid}/generate/prd?mode=template")
    assert resp.json()["version"] == 1

    # Second gen
    resp = await client.post(f"/api/projects/{pid}/generate/prd?mode=template")
    assert resp.json()["version"] == 2

    # Third gen
    resp = await client.post(f"/api/projects/{pid}/generate/prd?mode=template")
    assert resp.json()["version"] == 3


@pytest.mark.asyncio
async def test_generation_list_history(client: AsyncClient):
    """List generation history filtered by doc_type."""
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    # Generate a few docs
    for dt in ["prd", "fsd", "srs"]:
        await client.post(f"/api/projects/{pid}/generate/{dt}?mode=template")
    await client.post(f"/api/projects/{pid}/generate/prd?mode=template")
    await client.post(f"/api/projects/{pid}/generate/prd?mode=template")

    # List all
    resp = await client.get(f"/api/projects/{pid}/generations")
    assert resp.status_code == 200
    gens = resp.json()
    assert len(gens) == 5  # 3 unique + 2 extra PRD

    # Filter by doc_type
    resp = await client.get(f"/api/projects/{pid}/generations?doc_type=prd")
    assert resp.status_code == 200
    gens = resp.json()
    assert len(gens) == 3
    for g in gens:
        assert g["doc_type"] == "prd"


@pytest.mark.asyncio
async def test_trigger_generate_all(client: AsyncClient):
    """Trigger ALL document generation."""
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    resp = await client.post(f"/api/projects/{pid}/generate?mode=template")
    assert resp.status_code == 200
    data = resp.json()
    assert "generations" in data
    for dt in ["prd", "fsd", "srs", "erd", "sequence"]:
        assert dt in data["generations"]
        assert data["generations"][dt]["status"] == "pending"
        assert data["generations"][dt]["version"] == 1


@pytest.mark.asyncio
async def test_generation_404(client: AsyncClient):
    resp = await client.get("/api/projects/nonexistent/generations/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_doc_type_rejected(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    resp = await client.post(f"/api/projects/{pid}/generate/invalid")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_invalid_mode_rejected(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    resp = await client.post(f"/api/projects/{pid}/generate/prd?mode=invalid")
    assert resp.status_code == 422


# ─── Download ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_latest_completed(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    # Generate first
    gen_resp = await client.post(f"/api/projects/{pid}/generate/prd?mode=template")
    gen_id = gen_resp.json()["generation_id"]

    # Wait for completion
    import time
    for _ in range(10):
        sr = await client.get(f"/api/projects/{pid}/generations/{gen_id}/status")
        if sr.json()["status"] == "completed":
            break
        time.sleep(0.1)

    resp = await client.get(f"/api/projects/{pid}/download/prd")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "content-disposition" in resp.headers
    assert "attachment" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_download_specific_version(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    gen_resp = await client.post(f"/api/projects/{pid}/generate/prd?mode=template")
    gen_id = gen_resp.json()["generation_id"]

    import time
    for _ in range(10):
        sr = await client.get(f"/api/projects/{pid}/generations/{gen_id}/status")
        if sr.json()["status"] == "completed":
            break
        time.sleep(0.1)

    resp = await client.get(f"/api/projects/{pid}/download/gen/{gen_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")


@pytest.mark.asyncio
async def test_download_no_generation(client: AsyncClient):
    """Download should 404 if no generation exists."""
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]
    resp = await client.get(f"/api/projects/{pid}/download/prd")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_all_zip(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    # Generate all docs
    for dt in ["prd", "fsd", "srs", "erd", "sequence"]:
        gr = await client.post(f"/api/projects/{pid}/generate/{dt}?mode=template")
        gid = gr.json()["generation_id"]
        import time
        for _ in range(10):
            sr = await client.get(f"/api/projects/{pid}/generations/{gid}/status")
            if sr.json()["status"] == "completed":
                break
            time.sleep(0.1)

    resp = await client.get(f"/api/projects/{pid}/download-all")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]


# ─── Document Content Tests ──────────────────────────────

@pytest.mark.asyncio
async def test_prd_contains_expected_sections(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    # Generate and wait
    gr = await client.post(f"/api/projects/{pid}/generate/prd?mode=template")
    gid = gr.json()["generation_id"]
    import time
    for _ in range(10):
        sr = await client.get(f"/api/projects/{pid}/generations/{gid}/status")
        if sr.json()["status"] == "completed":
            break
        time.sleep(0.1)

    resp = await client.get(f"/api/projects/{pid}/generations/{gid}")
    md = resp.json()["content"]
    assert "# Product Requirements Document" in md
    assert "Stakeholders" in md or "Stakeholder" in md
    assert "Manajemen Stok" in md
    assert "Budi" in md


@pytest.mark.asyncio
async def test_srs_contains_non_functional_requirements(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    gr = await client.post(f"/api/projects/{pid}/generate/srs?mode=template")
    gid = gr.json()["generation_id"]
    import time
    for _ in range(10):
        sr = await client.get(f"/api/projects/{pid}/generations/{gid}/status")
        if sr.json()["status"] == "completed":
            break
        time.sleep(0.1)

    resp = await client.get(f"/api/projects/{pid}/generations/{gid}")
    md = resp.json()["content"]
    assert "Software Requirements Specification" in md
    assert "Performance Requirements" in md or "Non-Functional" in md


@pytest.mark.asyncio
async def test_erd_contains_entity_names(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    gr = await client.post(f"/api/projects/{pid}/generate/erd?mode=template")
    gid = gr.json()["generation_id"]
    import time
    for _ in range(10):
        sr = await client.get(f"/api/projects/{pid}/generations/{gid}/status")
        if sr.json()["status"] == "completed":
            break
        time.sleep(0.1)

    resp = await client.get(f"/api/projects/{pid}/generations/{gid}")
    md = resp.json()["content"]
    assert "User" in md
    assert "Product" in md


@pytest.mark.asyncio
async def test_sequence_contains_flow_title(client: AsyncClient):
    create_resp = await client.post("/api/projects", json=SAMPLE_PROJECT)
    pid = create_resp.json()["id"]

    gr = await client.post(f"/api/projects/{pid}/generate/sequence?mode=template")
    gid = gr.json()["generation_id"]
    import time
    for _ in range(10):
        sr = await client.get(f"/api/projects/{pid}/generations/{gid}/status")
        if sr.json()["status"] == "completed":
            break
        time.sleep(0.1)

    resp = await client.get(f"/api/projects/{pid}/generations/{gid}")
    md = resp.json()["content"]
    assert "Login Flow" in md


# ─── Edge Cases ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_project_no_relations(client: AsyncClient):
    """Minimal project with just a name."""
    resp = await client.post("/api/projects", json={"name": "Minimal Project"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Minimal Project"

    # Generate should still work
    pid = data["id"]
    gr = await client.post(f"/api/projects/{pid}/generate/prd?mode=template")
    gid = gr.json()["generation_id"]
    import time
    for _ in range(10):
        sr = await client.get(f"/api/projects/{pid}/generations/{gid}/status")
        if sr.json()["status"] == "completed":
            break
        time.sleep(0.1)

    resp = await client.get(f"/api/projects/{pid}/generations/{gid}")
    md = resp.json()["content"]
    assert "Minimal Project" in md


@pytest.mark.asyncio
async def test_long_project_name(client: AsyncClient):
    long_name = "A" * 200
    resp = await client.post("/api/projects", json={"name": long_name})
    assert resp.status_code == 201
    assert resp.json()["name"] == long_name


@pytest.mark.asyncio
async def test_special_chars_in_names(client: AsyncClient):
    resp = await client.post("/api/projects", json={
        "name": "Project <script>alert('xss')</script> & Co.",
        "stakeholders": [{"name": "User <b>Test</b>", "role": "Admin"}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "<script>" in data["name"]


@pytest.mark.asyncio
async def test_multiple_projects(client: AsyncClient):
    for i in range(5):
        resp = await client.post("/api/projects", json={"name": f"Project {i}"})
        assert resp.status_code == 201


# ─── AI Status ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_status(client: AsyncClient):
    """AI status endpoint exists and returns proper structure."""
    resp = await client.get("/api/ai/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "available" in data
    assert "configured" in data
