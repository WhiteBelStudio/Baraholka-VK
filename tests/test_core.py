from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

import database
from services.listings import ListingData, ListingStatus, validate_listing


class TestListingValidation(unittest.TestCase):
    def test_valid_listing(self):
        result = validate_listing(
            ListingData(
                title="Телефон",
                category="Электроника",
                description="Рабочий телефон, полный комплект.",
                price="1 999,99 ₽",
                city="Белореченск",
            )
        )
        self.assertEqual(result.price, "1999.99")

    def test_invalid_price(self):
        with self.assertRaises(Exception):
            validate_listing(
                ListingData("Телефон", "Электроника", "Нормальное описание", "abc", "Белореченск")
            )


class TestArchiveLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.sqlite3"
        self.patcher = patch.object(database.settings, "database_path", str(self.db_path))
        self.patcher.start()
        await database.init_db()

    async def asyncTearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    async def _insert_user(self, vk_id=1001):
        await database.execute(
            "INSERT INTO users (vk_user_id) VALUES (?)",
            (vk_id,),
        )
        row = await database.fetch_one("SELECT id FROM users WHERE vk_user_id = ?", (vk_id,))
        return int(row["id"])

    async def _insert_listing(self, user_id, status="published", post_id=77):
        await database.execute(
            "INSERT INTO listings "
            "(user_id, title, category, description, price, city, status, published_post_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, "Test", "Test", "Test description", "100", "Белореченск", status, post_id),
        )
        row = await database.fetch_one("SELECT id FROM listings ORDER BY id DESC LIMIT 1")
        return int(row["id"])

    async def test_archive_clears_vk_post_id(self):
        user_id = await self._insert_user()
        listing_id = await self._insert_listing(user_id)
        self.assertTrue(await database.archive_listing(listing_id))
        row = await database.get_listing(listing_id)
        self.assertEqual(row["status"], ListingStatus.ARCHIVED)
        self.assertIsNone(row["published_post_id"])

    async def test_restore_clears_vk_post_id(self):
        user_id = await self._insert_user(1002)
        listing_id = await self._insert_listing(user_id, "archived", None)
        self.assertTrue(await database.restore_archived_listing(listing_id))
        row = await database.get_listing(listing_id)
        self.assertEqual(row["status"], ListingStatus.APPROVED)
        self.assertIsNone(row["published_post_id"])


class TestVKClient(unittest.IsolatedAsyncioTestCase):
    async def test_wall_delete_is_called_for_published_archive(self):
        from services.moderation import archive_listing_for_admin

        listing = {
            "id": 1,
            "user_id": 1,
            "status": ListingStatus.PUBLISHED,
            "published_post_id": 77,
        }
        seller = {"vk_user_id": 1001}

        vk = AsyncMock()
        vk.call = AsyncMock()
        vk.send_message = AsyncMock()

        with patch("services.moderation.settings.can_moderate", return_value=True),              patch("services.moderation.get_listing", new=AsyncMock(return_value=listing)),              patch("services.moderation.get_user_by_internal_id", new=AsyncMock(return_value=seller)),              patch("services.moderation.archive_listing", new=AsyncMock(return_value=True)),              patch("services.moderation.add_moderation_log", new=AsyncMock()),              patch("services.moderation.add_admin_action_log", new=AsyncMock()):
            result, _ = await archive_listing_for_admin(1, 500, vk)

        self.assertIn("перемещено в архив", result)
        vk.call.assert_awaited_once_with("wall.delete", owner_id=-database.settings.vk_group_id, post_id=77)


if __name__ == "__main__":
    unittest.main()
