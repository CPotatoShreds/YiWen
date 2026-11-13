import type { Page } from "@playwright/test";

// 只供浏览器验收的样本，不进入应用或产品数据。
export const scenario = {
  id: "vol-1", slug: "night-ferry", name: "夜渡听潮", subtitle: "一灯照水，一苇过江",
  introduction: "暮色四合，渡口的末班船正要离岸。你须在第三声钟响之前，把一封未署名的信送到江心。",
  background: "雨停了，石阶尚湿。老船夫把灯笼往船头移了移，说今夜的潮声与往日不同。桥上有人撑着一柄旧伞，正等你走近。",
  rules: ["双方不得离开渡口与江面。", "渡船与信件不可损毁。"],
  victory_condition: "在第三声钟响之前，将信交给江心渡船上的船夫。",
  judgement_rules: ["必须由挑战者亲手交信。"], status: "published", created_by: 1,
};
export const ability = { id: "art-1", name: "借风", effect: "借一阵风，送一件轻物越过十步。", detail: "必须先屏息三息，落地后失去方向感一刻。" };
export const character = { id: "person-1", name: "沈听澜", bio: "在江边长大的送信人。记得每一处渡口，却总是忘记带伞。", ability_ids: [ability.id], owner_id: 1 };
export const roster = { id: "roster-1", name: "桥上旧伞", character_name: "撑伞客", character_bio: "一柄旧伞，半卷潮声。只说自己在等一位故人。", owner_name: "江边客", ability_count: 2, challenge_count: 4, challenger_win_rate: .5, first_victory_avg_challenges: 2 };
export const history = { id: "run-1", status: "won", won: true, created_at: "2026-11-12T09:00:00Z", challenger_character_name: character.name, strategy: "先问渡船何时开，再借风送信。" };
export const context = { scenario, roster, viewer_role: "challenger", my_progress: { attempts: 1, guess_count: 0, guess_credits: 1, cracked_cards: [{ index: 1, cracked: false }, { index: 2, cracked: false }] }, my_challenges: [history] };
export const challenge = { id: history.id, roster_id: roster.id, status: "won", won: true, scenario, roster, challenger: { character_name: character.name }, viewer_role: "challenger", god_unlocked: false, derived: { achieved: true, reason: "信已在第三声钟前交到船夫手中。" }, messages: [{ role: "views", challenger_text: "我踏过湿漉漉的石阶，远处传来第一声钟。\n撑伞的人没有回头，只把伞沿压低了一寸。风从伞下穿过，却在我面前忽然停了。\n我屏住呼吸，等那阵风重新走来。船上的灯轻轻一晃，信已稳稳落进船夫掌中。" }] };

export async function mockGame(page: Page, options: { empty?: boolean; failedVolumes?: boolean; reading?: boolean } = {}) {
  let characters = options.empty ? [] : [character];
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace(/^\/api/, "");
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    if (path === "/auth/me") return json({ id: 1, username: "枕溪", email: "reader@example.test", is_admin: false });
    if (path === "/scenarios" && options.failedVolumes) return json({ detail: "卷架暂不可用" }, 503);
    if (path === "/creator/characters" && req.method() === "POST") {
      const created = { ...req.postDataJSON(), id: "new-person", owner_id: 1 };
      characters = [...characters, created];
      return json(created, 201);
    }
    if (path.startsWith("/creator/characters/")) {
      const id = path.split("/").at(-1);
      if (req.method() === "DELETE") { characters = characters.filter(c => c.id !== id); return route.fulfill({ status: 204 }); }
      return json({ ...characters.find(c => c.id === id), abilities: options.empty ? [] : [ability] });
    }
    const routes: Record<string, unknown> = {
      "/scenarios": [scenario], [`/scenarios/${scenario.slug}`]: scenario,
      [`/scenarios/${scenario.slug}/rosters`]: [roster],
      [`/scenarios/${scenario.slug}/rosters/${roster.id}`]: options.reading ? { ...context, viewer_role: "both", my_challenges: [{ ...history, status: "resolving" }] } : context,
      "/creator/characters": characters, "/creator/abilities": options.empty ? [] : [ability],
      "/llm-profiles": [],
      "/auth/me/email": { email: "reader@example.test", verified: true },
      [`/scenario-challenges/${history.id}`]: options.reading ? { ...challenge, viewer_role: "both", god_unlocked: true, messages: [{ ...challenge.messages[0], guardian_text: "我收起伞，目送那封信穿过江风。", omniscient: "送信人在钟响之前借风渡江，将信交付。" }] } : challenge,
    };
    if (path.endsWith("/stream")) return route.fulfill({ contentType: "text/event-stream", body: 'data: {"type":"done","status":"won"}\n\n' });
    if (path in routes) return json(routes[path]);
    return json({ detail: `Unmocked endpoint: ${path}` }, 404);
  });
}
