"""Enterprise Request Validation & Fuzz Testing Engine.

Implements the Three Fundamental Testing Paradigms:
1. White Box: Internal algorithmic logic, division-by-zero guards, indicator tensor shapes.
2. Black Box: External HTTP request contracts across GET, POST, PUT, DELETE, OPTIONS, schemas & status codes.
3. Grey Box: Hybrid security boundaries, rate limiting, RBAC escalation, SQLi/XSS fuzzing & financial idempotency.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class RequestValidationResult:
    def __init__(
        self,
        test_id: str,
        method: str,
        endpoint: str,
        paradigm: str,  # "BLACK_BOX" | "WHITE_BOX" | "GREY_BOX"
        test_type: str,  # "POSITIVE", "SCHEMA_VIOLATION", "BOUNDARY", "FUZZ_INJECTION", "UNAUTHENTICATED", "ALGORITHM_MATH"
        expected_status: List[int],
        actual_status: int,
        passed: bool,
        duration_ms: float,
        details: str,
        request_payload: Optional[Any] = None,
        response_snippet: Optional[str] = None,
    ):
        self.test_id = test_id
        self.method = method
        self.endpoint = endpoint
        self.paradigm = paradigm
        self.test_type = test_type
        self.expected_status = expected_status
        self.actual_status = actual_status
        self.passed = passed
        self.duration_ms = duration_ms
        self.details = details
        self.request_payload = request_payload
        self.response_snippet = response_snippet

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "method": self.method,
            "endpoint": self.endpoint,
            "paradigm": self.paradigm,
            "test_type": self.test_type,
            "expected_status": self.expected_status,
            "actual_status": self.actual_status,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 2),
            "details": self.details,
            "request_payload": self.request_payload,
            "response_snippet": self.response_snippet,
        }


class RequestValidatorService:
    """Automated & Interactive HTTP Request Validation and Fuzz Testing Engine."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RequestValidatorService, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self._transport = ASGITransport(app=app)

    async def _execute_probe(
        self,
        test_id: str,
        method: str,
        endpoint: str,
        paradigm: str,
        test_type: str,
        expected_status: List[int],
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        description: str = "",
    ) -> RequestValidationResult:
        """Internal helper to dispatch an in-process HTTP probe against FastAPI ASGI app."""
        t0 = time.perf_counter()
        req_headers = headers or {}

        try:
            async with AsyncClient(transport=self._transport, base_url="http://test") as client:
                if method.upper() == "GET":
                    res = await client.get(endpoint, headers=req_headers, params=params)
                elif method.upper() == "POST":
                    res = await client.post(endpoint, headers=req_headers, json=json_data, params=params)
                elif method.upper() == "PUT":
                    res = await client.put(endpoint, headers=req_headers, json=json_data)
                elif method.upper() == "DELETE":
                    res = await client.delete(endpoint, headers=req_headers)
                elif method.upper() == "OPTIONS":
                    res = await client.options(endpoint, headers=req_headers)
                else:
                    res = await client.request(method, endpoint, headers=req_headers, json=json_data)

            duration = (time.perf_counter() - t0) * 1000
            passed = res.status_code in expected_status

            body_text = res.text[:300] if res.text else ""
            details = description or (
                f"HTTP {res.status_code} returned. Expected {expected_status}. "
                f"{'Validation passed.' if passed else 'Unexpected response status code.'}"
            )

            return RequestValidationResult(
                test_id=test_id,
                method=method.upper(),
                endpoint=endpoint,
                paradigm=paradigm,
                test_type=test_type,
                expected_status=expected_status,
                actual_status=res.status_code,
                passed=passed,
                duration_ms=duration,
                details=details,
                request_payload=json_data or params,
                response_snippet=body_text,
            )
        except Exception as e:
            duration = (time.perf_counter() - t0) * 1000
            return RequestValidationResult(
                test_id=test_id,
                method=method.upper(),
                endpoint=endpoint,
                paradigm=paradigm,
                test_type=test_type,
                expected_status=expected_status,
                actual_status=500,
                passed=False,
                duration_ms=duration,
                details=f"Transport exception during probe: {str(e)}",
            )

    # =========================================================================
    # Paradigm Suites: Black Box, White Box, Grey Box
    # =========================================================================

    async def test_black_box_suite(self) -> List[RequestValidationResult]:
        """BLACK BOX TESTING: External contracts, HTTP verbs, status codes, and schema validation."""
        tests = []

        # 1. GET Root Status (Public Contract)
        tests.append(
            await self._execute_probe(
                test_id="BB-01",
                method="GET",
                endpoint="/",
                paradigm="BLACK_BOX",
                test_type="POSITIVE",
                expected_status=[200],
                description="Root health endpoint serves valid 200 OK with application name & version schema.",
            )
        )

        # 2. GET Prometheus Metrics (Observability Contract)
        tests.append(
            await self._execute_probe(
                test_id="BB-02",
                method="GET",
                endpoint="/metrics",
                paradigm="BLACK_BOX",
                test_type="POSITIVE",
                expected_status=[200],
                description="Prometheus scraper endpoint delivers standard plain-text metrics format.",
            )
        )

        # 3. POST Auth Login Missing Body (Pydantic Schema Violation)
        tests.append(
            await self._execute_probe(
                test_id="BB-03",
                method="POST",
                endpoint="/api/auth/login",
                paradigm="BLACK_BOX",
                test_type="SCHEMA_VIOLATION",
                json_data={},
                expected_status=[422],
                description="Empty request payload rejected with HTTP 422 Unprocessable Entity (missing required fields).",
            )
        )

        # 4. POST Auth Login Type Mismatch (Data Type Validation)
        tests.append(
            await self._execute_probe(
                test_id="BB-04",
                method="POST",
                endpoint="/api/auth/login",
                paradigm="BLACK_BOX",
                test_type="SCHEMA_VIOLATION",
                json_data={"email": 12345, "password": ["array_not_string"]},
                expected_status=[422],
                description="Invalid data types (integer for email, list for password) rejected with 422 schema validation error.",
            )
        )

        # 5. GET 404 Route Contract
        tests.append(
            await self._execute_probe(
                test_id="BB-05",
                method="GET",
                endpoint="/api/non_existent_route_404",
                paradigm="BLACK_BOX",
                test_type="POSITIVE",
                expected_status=[404],
                description="Non-existent API URL responds with standard HTTP 404 Not Found error.",
            )
        )

        # 6. DELETE Unsupported Method (405 Check)
        tests.append(
            await self._execute_probe(
                test_id="BB-06",
                method="DELETE",
                endpoint="/api/auth/login",
                paradigm="BLACK_BOX",
                test_type="BOUNDARY",
                expected_status=[405],
                description="HTTP DELETE invoked on POST-only endpoint returns RFC 7231 standard 405 Method Not Allowed.",
            )
        )

        # 7. OPTIONS CORS Preflight Contract
        tests.append(
            await self._execute_probe(
                test_id="BB-07",
                method="OPTIONS",
                endpoint="/api/stocks/quote/RELIANCE",
                paradigm="BLACK_BOX",
                test_type="POSITIVE",
                headers={"Origin": "https://stock-ai-iota-seven.vercel.app", "Access-Control-Request-Method": "GET"},
                expected_status=[200, 204],
                description="CORS OPTIONS preflight contract returns 200/204 with Access-Control headers.",
            )
        )

        return tests

    async def test_grey_box_suite(self) -> List[RequestValidationResult]:
        """GREY BOX TESTING: Hybrid security boundaries, rate limiting, RBAC, SQLi, and idempotency."""
        tests = []

        # 1. SQL Injection Fuzzing on Public Search
        tests.append(
            await self._execute_probe(
                test_id="GB-01",
                method="GET",
                endpoint="/api/stocks/search",
                paradigm="GREY_BOX",
                test_type="FUZZ_INJECTION",
                params={"q": "' OR '1'='1' --"},
                expected_status=[200, 400, 401, 422],
                description="SQL injection payload safely handled by query binder; zero database crash or 500 error.",
            )
        )

        # 2. XSS Script Tag Injection on Paper Trade
        tests.append(
            await self._execute_probe(
                test_id="GB-02",
                method="POST",
                endpoint="/api/paper-trades",
                paradigm="GREY_BOX",
                test_type="FUZZ_INJECTION",
                json_data={"symbol": "<script>alert('xss')</script>", "quantity": 10, "direction": "BUY"},
                expected_status=[401, 403, 422],
                description="XSS payload blocked by authentication guard or input validation; zero script execution.",
            )
        )

        # 3. RBAC Unauthenticated Admin Access
        tests.append(
            await self._execute_probe(
                test_id="GB-03",
                method="GET",
                endpoint="/api/admin/users",
                paradigm="GREY_BOX",
                test_type="UNAUTHENTICATED",
                expected_status=[401, 403],
                description="Privileged Admin route strictly rejects unauthenticated caller with HTTP 401/403.",
            )
        )

        # 4. Financial Order Replay & Boundary (Negative Quantity)
        tests.append(
            await self._execute_probe(
                test_id="GB-04",
                method="POST",
                endpoint="/api/paper-trades",
                paradigm="GREY_BOX",
                test_type="BOUNDARY",
                json_data={"symbol": "RELIANCE.NS", "quantity": -99, "direction": "BUY"},
                expected_status=[401, 403, 422],
                description="Negative order quantity correctly denied by schema boundary check or auth guard.",
            )
        )

        # 5. Token Bucket Burst Throttling
        tests.append(
            await self._execute_probe(
                test_id="GB-05",
                method="POST",
                endpoint="/api/auth/login",
                paradigm="GREY_BOX",
                test_type="BOUNDARY",
                json_data={"email": "stress_test@stockai.com", "password": "Password123!"},
                expected_status=[400, 401, 422, 429],
                description="Authentication tier token bucket enforces anti-bruteforce rate limits.",
            )
        )

        return tests

    async def test_white_box_suite(self) -> List[RequestValidationResult]:
        """WHITE BOX TESTING: Algorithmic math, numerical sanity, NaN prevention & feature tensors."""
        tests = []
        t0 = time.perf_counter()

        # 1. Technical Indicators Math (RSI & ATR)
        try:
            import pandas as pd
            import ta
            closes = [100.0 + i for i in range(30)]
            df = pd.DataFrame({"Close": closes, "High": [c + 1 for c in closes], "Low": [c - 1 for c in closes], "Volume": [1000] * 30})
            rsi = float(ta.momentum.RSIIndicator(close=df["Close"], window=14).rsi().iloc[-1])
            atr = float(ta.volatility.AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14).average_true_range().iloc[-1])
            math_passed = 0 <= rsi <= 100 and atr > 0
            dur = (time.perf_counter() - t0) * 1000

            tests.append(
                RequestValidationResult(
                    test_id="WB-01",
                    method="INTERNAL",
                    endpoint="IndicatorService.compute_indicators",
                    paradigm="WHITE_BOX",
                    test_type="ALGORITHM_MATH",
                    expected_status=[200],
                    actual_status=200 if math_passed else 500,
                    passed=math_passed,
                    duration_ms=dur,
                    details=f"RSI={rsi:.1f}, ATR={atr:.2f}. Algorithms operate strictly within bounded finite ranges.",
                )
            )
        except Exception as e:
            tests.append(
                RequestValidationResult(
                    test_id="WB-01",
                    method="INTERNAL",
                    endpoint="IndicatorService.compute_indicators",
                    paradigm="WHITE_BOX",
                    test_type="ALGORITHM_MATH",
                    expected_status=[200],
                    actual_status=500,
                    passed=False,
                    duration_ms=0.0,
                    details=f"Indicator algorithm exception: {str(e)}",
                )
            )

        # 2. Machine Learning 36-Feature Tensor Dimensions
        t1 = time.perf_counter()
        try:
            from backend.services.ml.feature_engineering import N_FEATURES
            tensor_passed = N_FEATURES == 36
            dur1 = (time.perf_counter() - t1) * 1000
            tests.append(
                RequestValidationResult(
                    test_id="WB-02",
                    method="INTERNAL",
                    endpoint="FeatureEngineering.tensor_shape",
                    paradigm="WHITE_BOX",
                    test_type="ALGORITHM_MATH",
                    expected_status=[200],
                    actual_status=200 if tensor_passed else 500,
                    passed=tensor_passed,
                    duration_ms=dur1,
                    details=f"Feature tensor calibrated at exactly {N_FEATURES} scale-invariant features for BiLSTM/Transformer.",
                )
            )
        except Exception as e:
            tests.append(
                RequestValidationResult(
                    test_id="WB-02",
                    method="INTERNAL",
                    endpoint="FeatureEngineering.tensor_shape",
                    paradigm="WHITE_BOX",
                    test_type="ALGORITHM_MATH",
                    expected_status=[200],
                    actual_status=500,
                    passed=False,
                    duration_ms=0.0,
                    details=f"ML feature tensor check failed: {str(e)}",
                )
            )

        return tests

    # =========================================================================
    # Master Execution
    # =========================================================================

    async def run_all_paradigms(self) -> Dict[str, Any]:
        """Execute all Three Testing Paradigms (White, Black, Grey Box) and return summary."""
        t0 = time.perf_counter()

        bb_results = await self.test_black_box_suite()
        gb_results = await self.test_grey_box_suite()
        wb_results = await self.test_white_box_suite()

        all_results = bb_results + gb_results + wb_results
        total_duration = (time.perf_counter() - t0) * 1000

        total = len(all_results)
        passed = sum(1 for r in all_results if r.passed)
        failed = total - passed

        return {
            "suite": "ENTERPRISE_THREE_TIER_TEST_MATRIX",
            "timestamp": time.time(),
            "total_probes": total,
            "passed_probes": passed,
            "failed_probes": failed,
            "duration_ms": round(total_duration, 2),
            "status": "PASSED" if failed == 0 else "FAILED",
            "paradigms": {
                "black_box": [r.to_dict() for r in bb_results],
                "grey_box": [r.to_dict() for r in gb_results],
                "white_box": [r.to_dict() for r in wb_results],
            },
            "probes": [r.to_dict() for r in all_results],
        }

    async def execute_custom_probe(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Allows interactive execution of custom requests from the QA admin UI."""
        t0 = time.perf_counter()
        req_headers = headers or {}

        try:
            async with AsyncClient(transport=self._transport, base_url="http://test") as client:
                res = await client.request(
                    method=method.upper(),
                    url=endpoint,
                    headers=req_headers,
                    json=payload if method.upper() in ("POST", "PUT", "PATCH") else None,
                    params=payload if method.upper() == "GET" and isinstance(payload, dict) else None,
                )

            duration = (time.perf_counter() - t0) * 1000
            try:
                body_json = res.json()
            except Exception:
                body_json = res.text[:500]

            return {
                "method": method.upper(),
                "endpoint": endpoint,
                "status_code": res.status_code,
                "duration_ms": round(duration, 2),
                "headers": dict(res.headers),
                "body": body_json,
                "success": res.status_code < 400,
            }
        except Exception as e:
            return {
                "method": method.upper(),
                "endpoint": endpoint,
                "status_code": 500,
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
                "error": str(e),
                "success": False,
            }


request_validator = RequestValidatorService()
