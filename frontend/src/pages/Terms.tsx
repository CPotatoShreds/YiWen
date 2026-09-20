import { Link } from "react-router-dom";
import { SealStamp } from "../components/Ornaments";

/** 静态文本页（P3）：协议正文为模板占位，正式上线前需经法务/业务侧审阅替换。 */
export default function Terms() {
  return (
    <div className="auth">
      <div className="auth__card rise" style={{ maxWidth: 720 }}>
        <div className="auth__brand">
          <span className="brand__mark">
            <SealStamp char="异" size={40} />
          </span>
          <h1>用户协议</h1>
        </div>
        <div style={{ lineHeight: 1.9, fontSize: 14, textAlign: "left" }}>
          <p><strong>1. 服务性质。</strong>异闻录是面向个人玩家的 AI 奇术对战平台。平台提供基于大语言模型的推演、点评与转写服务，生成内容为虚构创作，不代表任何现实立场。</p>
          <p><strong>2. 账号。</strong>你需为账号与口令保管负责。平台提供密码找回（需绑定邮箱）与账号注销（设置页）能力；注销后账号将被匿名化，不可恢复。</p>
          <p><strong>3. 用户内容。</strong>你通过平台创作的奇术、奇人与阵容，其所有权归你；你授予平台为提供对战、推演与展示服务所必需的使用许可。不得录入违法违规或侵犯他人权益的内容。</p>
          <p><strong>4. 使用限制。</strong>不得以自动化脚本批量请求、干扰服务正常运行；平台对接口实施限流与滥用防护。</p>
          <p><strong>5. 服务变更与终止。</strong>平台可随产品演进调整服务范围；对违反本协议的账号，平台有权采取限制措施。</p>
          <p className="muted">本协议为模板文本，正式运营前请经法务审阅替换。</p>
        </div>
        <p className="auth__foot">
          <Link to="/">返回首页</Link>
          <span className="muted">　·　</span>
          <Link to="/privacy">隐私政策</Link>
        </p>
      </div>
    </div>
  );
}
