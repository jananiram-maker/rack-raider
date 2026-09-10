"""
BigQuery Analytics Data Warehouse Client for naturallyEasy.
Manages schema definitions, asynchronous ingestion of Items, Outfits, and Outfit_Items junction records,
and executes analytical SQL queries (wear frequency, co-occurrence, seasonal underutilization).
"""

from typing import List, Dict, Any, Optional
import json
import time
from collections import defaultdict
from ..config import (
    GCP_PROJECT_ID,
    BIGQUERY_DATASET,
    BIGQUERY_TABLE_ITEMS,
    BIGQUERY_TABLE_OUTFITS,
    BIGQUERY_TABLE_OUTFIT_ITEMS,
    get_bq_table_id
)
from ..auth import validate_user_access

# Try importing real BigQuery client
try:
    from google.cloud import bigquery
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False


class BigQueryWardrobeClient:
    """
    Analytics client managing BigQuery warehouse tables and analytical queries.
    """
    def __init__(self, project_id: str = GCP_PROJECT_ID, dataset_id: str = BIGQUERY_DATASET, use_mock: bool = False):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self._client = None
        self._use_mock = use_mock or (not BIGQUERY_AVAILABLE)

        # In-memory tables for local testing & mock analytics: {table_name: [rows]}
        self._mock_tables: Dict[str, List[Dict[str, Any]]] = {
            BIGQUERY_TABLE_ITEMS: [],
            BIGQUERY_TABLE_OUTFITS: [],
            BIGQUERY_TABLE_OUTFIT_ITEMS: []
        }

        if not self._use_mock:
            try:
                self._client = bigquery.Client(project=self.project_id)
            except Exception as e:
                print(f"[BigQuery] Live client initialization failed: {e}. Falling back to in-memory store.")
                self._use_mock = True

    # ---------------------------------------------------------------------------
    # Schema Definitions
    # ---------------------------------------------------------------------------
    @staticmethod
    def get_items_schema():
        if not BIGQUERY_AVAILABLE:
            return []
        return [
            bigquery.SchemaField("item_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("occasion", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("material", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("season_tag", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("wear_frequency_expectation", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("embedding_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("item_gs_uri", "STRING", mode="NULLABLE"),
        ]

    @staticmethod
    def get_outfits_schema():
        if not BIGQUERY_AVAILABLE:
            return []
        return [
            bigquery.SchemaField("outfit_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("worn_date", "DATE", mode="REQUIRED"),
            bigquery.SchemaField("occasion", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("weather_summary", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("outfit_gs_uri", "STRING", mode="NULLABLE"),
        ]

    @staticmethod
    def get_outfit_items_schema():
        if not BIGQUERY_AVAILABLE:
            return []
        return [
            bigquery.SchemaField("outfit_item_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("outfit_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("item_id", "STRING", mode="REQUIRED"),
        ]

    # ---------------------------------------------------------------------------
    # Ingestion Methods
    # ---------------------------------------------------------------------------
    def insert_items(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Inserts items into the BigQuery Items table.
        """
        if not rows:
            return {"status": "success", "inserted_count": 0}

        # Filter strictly to schema columns
        cleaned_rows = []
        for r in rows:
            cleaned_rows.append({
                "item_id": str(r.get("item_id")),
                "user_id": str(r.get("user_id")),
                "category": str(r.get("category", "Top")),
                "occasion": str(r.get("occasion", "Casual / Daily")),
                "material": str(r.get("material", "Unknown")),
                "season_tag": str(r.get("season_tag") or r.get("season") or "All-Season"),
                "wear_frequency_expectation": str(r.get("wear_frequency_expectation", "Weekly")),
                "embedding_id": str(r.get("embedding_id") or r.get("item_id")),
                "item_gs_uri": str(r.get("item_gs_uri") or r.get("gcs_uri") or "")
            })

        if self._use_mock:
            self._mock_tables[BIGQUERY_TABLE_ITEMS].extend(cleaned_rows)
            return {"status": "success", "inserted_count": len(cleaned_rows)}

        table_id = get_bq_table_id(BIGQUERY_TABLE_ITEMS, self.project_id, self.dataset_id)
        errors = self._client.insert_rows_json(table_id, cleaned_rows)
        if errors:
            raise RuntimeError(f"BigQuery Items insert failed: {errors}")
        return {"status": "success", "inserted_count": len(cleaned_rows)}

    def insert_outfits(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Inserts outfits into the BigQuery Outfits table.
        """
        if not rows:
            return {"status": "success", "inserted_count": 0}

        cleaned_rows = []
        for r in rows:
            weather_val = r.get("weather_summary", "")
            if isinstance(weather_val, dict):
                weather_val = json.dumps(weather_val)

            cleaned_rows.append({
                "outfit_id": str(r.get("outfit_id")),
                "user_id": str(r.get("user_id")),
                "worn_date": str(r.get("worn_date") or time.strftime("%Y-%m-%d")),
                "occasion": str(r.get("occasion", "Casual / Daily")),
                "weather_summary": str(weather_val),
                "outfit_gs_uri": str(r.get("outfit_gs_uri") or "")
            })

        if self._use_mock:
            self._mock_tables[BIGQUERY_TABLE_OUTFITS].extend(cleaned_rows)
            return {"status": "success", "inserted_count": len(cleaned_rows)}

        table_id = get_bq_table_id(BIGQUERY_TABLE_OUTFITS, self.project_id, self.dataset_id)
        errors = self._client.insert_rows_json(table_id, cleaned_rows)
        if errors:
            raise RuntimeError(f"BigQuery Outfits insert failed: {errors}")
        return {"status": "success", "inserted_count": len(cleaned_rows)}

    def insert_outfit_items(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Inserts junction mappings into the BigQuery Outfit_Items table.
        """
        if not rows:
            return {"status": "success", "inserted_count": 0}

        cleaned_rows = []
        for r in rows:
            cleaned_rows.append({
                "outfit_item_id": str(r.get("outfit_item_id") or f"{r.get('outfit_id')}_{r.get('item_id')}"),
                "outfit_id": str(r.get("outfit_id")),
                "item_id": str(r.get("item_id"))
            })

        if self._use_mock:
            self._mock_tables[BIGQUERY_TABLE_OUTFIT_ITEMS].extend(cleaned_rows)
            return {"status": "success", "inserted_count": len(cleaned_rows)}

        table_id = get_bq_table_id(BIGQUERY_TABLE_OUTFIT_ITEMS, self.project_id, self.dataset_id)
        errors = self._client.insert_rows_json(table_id, cleaned_rows)
        if errors:
            raise RuntimeError(f"BigQuery Outfit_Items insert failed: {errors}")
        return {"status": "success", "inserted_count": len(cleaned_rows)}

    def delete_item(self, item_id: str) -> Dict[str, Any]:
        """
        Deletes an item and all associated outfit_items records from BigQuery.
        """
        if self._use_mock:
            self._mock_tables[BIGQUERY_TABLE_ITEMS] = [
                i for i in self._mock_tables[BIGQUERY_TABLE_ITEMS] if i["item_id"] != item_id
            ]
            self._mock_tables[BIGQUERY_TABLE_OUTFIT_ITEMS] = [
                oi for oi in self._mock_tables[BIGQUERY_TABLE_OUTFIT_ITEMS] if oi["item_id"] != item_id
            ]
            return {"status": "success", "deleted_item": item_id}

        items_tbl = get_bq_table_id(BIGQUERY_TABLE_ITEMS, self.project_id, self.dataset_id)
        outfit_items_tbl = get_bq_table_id(BIGQUERY_TABLE_OUTFIT_ITEMS, self.project_id, self.dataset_id)

        try:
            # Delete from outfit_items first (foreign key)
            delete_oi_query = f"DELETE FROM `{outfit_items_tbl}` WHERE item_id = @item_id"
            job_config = bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("item_id", "STRING", item_id)]
            )
            self._client.query(delete_oi_query, job_config=job_config).result()

            # Then delete from items
            delete_i_query = f"DELETE FROM `{items_tbl}` WHERE item_id = @item_id"
            self._client.query(delete_i_query, job_config=job_config).result()

            return {"status": "success", "deleted_item": item_id}
        except Exception as e:
            raise RuntimeError(f"BigQuery item deletion failed: {e}")

    # ---------------------------------------------------------------------------
    # Analytics SQL Helpers
    # ---------------------------------------------------------------------------
    def query_item_wear_frequency(
        self,
        user_id: str,
        days_lookback: int = 90,
        auth_user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Calculates item wear frequency, total times worn, and wear rate for the specified user.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        if self._use_mock:
            # Calculate mock frequency across tables
            user_items = [i for i in self._mock_tables[BIGQUERY_TABLE_ITEMS] if i["user_id"] == user_id]
            user_outfits = {o["outfit_id"]: o for o in self._mock_tables[BIGQUERY_TABLE_OUTFITS] if o["user_id"] == user_id}
            
            wear_counts = defaultdict(int)
            for oi in self._mock_tables[BIGQUERY_TABLE_OUTFIT_ITEMS]:
                if oi["outfit_id"] in user_outfits:
                    wear_counts[oi["item_id"]] += 1

            results = []
            for item in user_items:
                w_count = wear_counts[item["item_id"]]
                results.append({
                    "item_id": item["item_id"],
                    "category": item["category"],
                    "occasion": item["occasion"],
                    "total_wears": w_count,
                    "wear_frequency_expectation": item["wear_frequency_expectation"],
                    "wear_rate_per_month": round((w_count / max(days_lookback, 1)) * 30, 2)
                })
            return sorted(results, key=lambda x: x["total_wears"], reverse=True)

        items_tbl = get_bq_table_id(BIGQUERY_TABLE_ITEMS, self.project_id, self.dataset_id)
        outfits_tbl = get_bq_table_id(BIGQUERY_TABLE_OUTFITS, self.project_id, self.dataset_id)
        outfit_items_tbl = get_bq_table_id(BIGQUERY_TABLE_OUTFIT_ITEMS, self.project_id, self.dataset_id)

        query = f"""
        SELECT 
            i.item_id,
            i.category,
            i.occasion,
            i.wear_frequency_expectation,
            COUNT(oi.outfit_id) AS total_wears,
            ROUND((COUNT(oi.outfit_id) / @days_lookback) * 30, 2) AS wear_rate_per_month
        FROM `{items_tbl}` i
        LEFT JOIN `{outfit_items_tbl}` oi ON i.item_id = oi.item_id
        LEFT JOIN `{outfits_tbl}` o ON oi.outfit_id = o.outfit_id
        WHERE i.user_id = @user_id
          AND (o.worn_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days_lookback DAY) OR o.worn_date IS NULL)
        GROUP BY 1, 2, 3, 4
        ORDER BY total_wears DESC
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
                bigquery.ScalarQueryParameter("days_lookback", "INT64", days_lookback),
            ]
        )
        query_job = self._client.query(query, job_config=job_config)
        return [dict(row) for row in query_job]

    def query_cooccurrence_matrix(
        self,
        user_id: str,
        min_cooccurrence: int = 1,
        auth_user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Computes pairwise garment co-occurrence frequencies (which items are paired most often).
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        if self._use_mock:
            user_outfits = {o["outfit_id"]: o for o in self._mock_tables[BIGQUERY_TABLE_OUTFITS] if o["user_id"] == user_id}
            outfit_to_items = defaultdict(list)
            for oi in self._mock_tables[BIGQUERY_TABLE_OUTFIT_ITEMS]:
                if oi["outfit_id"] in user_outfits:
                    outfit_to_items[oi["outfit_id"]].append(oi["item_id"])

            pair_counts = defaultdict(int)
            for outfit_id, items in outfit_to_items.items():
                sorted_items = sorted(set(items))
                for i in range(len(sorted_items)):
                    for j in range(i + 1, len(sorted_items)):
                        pair_counts[(sorted_items[i], sorted_items[j])] += 1

            results = []
            for (item_a, item_b), count in pair_counts.items():
                if count >= min_cooccurrence:
                    results.append({
                        "item_a_id": item_a,
                        "item_b_id": item_b,
                        "cooccurrence_count": count
                    })
            return sorted(results, key=lambda x: x["cooccurrence_count"], reverse=True)

        items_tbl = get_bq_table_id(BIGQUERY_TABLE_ITEMS, self.project_id, self.dataset_id)
        outfits_tbl = get_bq_table_id(BIGQUERY_TABLE_OUTFITS, self.project_id, self.dataset_id)
        outfit_items_tbl = get_bq_table_id(BIGQUERY_TABLE_OUTFIT_ITEMS, self.project_id, self.dataset_id)

        query = f"""
        WITH user_outfit_items AS (
            SELECT oi.outfit_id, oi.item_id
            FROM `{outfit_items_tbl}` oi
            JOIN `{outfits_tbl}` o ON oi.outfit_id = o.outfit_id
            WHERE o.user_id = @user_id
        )
        SELECT 
            a.item_id AS item_a_id,
            b.item_id AS item_b_id,
            COUNT(1) AS cooccurrence_count
        FROM user_outfit_items a
        JOIN user_outfit_items b 
          ON a.outfit_id = b.outfit_id AND a.item_id < b.item_id
        GROUP BY 1, 2
        HAVING cooccurrence_count >= @min_cooccurrence
        ORDER BY cooccurrence_count DESC
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
                bigquery.ScalarQueryParameter("min_cooccurrence", "INT64", min_cooccurrence),
            ]
        )
        query_job = self._client.query(query, job_config=job_config)
        return [dict(row) for row in query_job]

    def query_underutilized_seasonal_flags(
        self,
        user_id: str,
        current_season: str = "Summer",
        auth_user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Identifies in-season garments that have zero or critically low wears during the current active season.
        """
        if auth_user_id:
            validate_user_access(auth_user_id, user_id)

        if self._use_mock:
            user_items = [i for i in self._mock_tables[BIGQUERY_TABLE_ITEMS] if i["user_id"] == user_id]
            user_outfits = {o["outfit_id"]: o for o in self._mock_tables[BIGQUERY_TABLE_OUTFITS] if o["user_id"] == user_id}
            
            wear_counts = defaultdict(int)
            for oi in self._mock_tables[BIGQUERY_TABLE_OUTFIT_ITEMS]:
                if oi["outfit_id"] in user_outfits:
                    wear_counts[oi["item_id"]] += 1

            flagged = []
            for item in user_items:
                season = item.get("season_tag", "All-Season")
                if current_season in season or season == "All-Season":
                    wears = wear_counts[item["item_id"]]
                    if wears == 0:
                        flagged.append({
                            "item_id": item["item_id"],
                            "category": item["category"],
                            "season_tag": season,
                            "wear_count": wears,
                            "underutilized_reason": f"Active in {current_season} but has 0 recorded wears."
                        })
            return flagged

        items_tbl = get_bq_table_id(BIGQUERY_TABLE_ITEMS, self.project_id, self.dataset_id)
        outfits_tbl = get_bq_table_id(BIGQUERY_TABLE_OUTFITS, self.project_id, self.dataset_id)
        outfit_items_tbl = get_bq_table_id(BIGQUERY_TABLE_OUTFIT_ITEMS, self.project_id, self.dataset_id)

        query = f"""
        SELECT 
            i.item_id,
            i.category,
            i.season_tag,
            COUNT(oi.outfit_id) AS wear_count,
            'Active season item with zero or low wears' AS underutilized_reason
        FROM `{items_tbl}` i
        LEFT JOIN `{outfit_items_tbl}` oi ON i.item_id = oi.item_id
        LEFT JOIN `{outfits_tbl}` o ON oi.outfit_id = o.outfit_id AND o.user_id = @user_id
        WHERE i.user_id = @user_id
          AND (i.season_tag LIKE CONCAT('%', @current_season, '%') OR i.season_tag = 'All-Season')
        GROUP BY 1, 2, 3
        HAVING wear_count = 0
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
                bigquery.ScalarQueryParameter("current_season", "STRING", current_season),
            ]
        )
        query_job = self._client.query(query, job_config=job_config)
        return [dict(row) for row in query_job]


# Global singleton instance
_BIGQUERY_CLIENT_INSTANCE: Optional[BigQueryWardrobeClient] = None

def get_bigquery_client(force_mock: bool = False) -> BigQueryWardrobeClient:
    global _BIGQUERY_CLIENT_INSTANCE
    if _BIGQUERY_CLIENT_INSTANCE is None:
        _BIGQUERY_CLIENT_INSTANCE = BigQueryWardrobeClient(use_mock=force_mock)
    return _BIGQUERY_CLIENT_INSTANCE
