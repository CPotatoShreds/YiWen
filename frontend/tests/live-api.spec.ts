import { randomBytes } from "node:crypto";
import { test, expect } from "@playwright/test";

// 指向隔离开发库才启用：注册临时用户，测试完成后注销；不调用 LLM。
test("真实 API：创建奇人、刷新读取、删除与缓存同步", async ({ page }) => {
  test.skip(process.env.E2E_LIVE_API !== "1", "Requires a backend connected to an isolated review database");
  const username = `review_${randomBytes(5).toString("hex")}`;
  const password = randomBytes(24).toString("hex");
  const registered = await page.request.post("/api/auth/register", { data: { username, password, email: `${username}@example.com` } });
  expect(registered.status()).toBe(201);
  expect((await page.request.post("/api/auth/login", { data: { username, password } })).ok()).toBe(true);
  try {
    await page.goto("/yiwenlu");
    await page.getByRole("button", { name: "写一位奇人" }).click();
    await page.getByRole("textbox", { name: "名字" }).fill("临江听雨");
    await page.getByRole("button", { name: "收录", exact: true }).click();
    await expect(page.getByRole("heading", { name: "临江听雨" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "临江听雨" })).toBeVisible();
    await page.getByRole("button", { name: "编辑 临江听雨" }).click();
    await page.getByRole("button", { name: "删除", exact: true }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "确认继续" }).click();
    await expect(page.getByRole("heading", { name: "异闻录尚是空白" })).toBeVisible();
    const characters = await page.request.get("/api/creator/characters");
    expect(await characters.json()).toEqual([]);
  } finally {
    expect((await page.request.delete("/api/auth/me", { data: { password } })).status()).toBe(204);
  }
});
