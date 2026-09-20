import { Link } from "react-router-dom";
import { SealStamp } from "../components/Ornaments";

/** 静态文本页（P3）：政策正文为模板占位，正式上线前需经法务/业务侧审阅替换。 */
export default function Privacy() {
  return (
    <div className="auth">
      <div className="auth__card rise" style={{ maxWidth: 720 }}>
        <div className="auth__brand">
          <span className="brand__mark">
            <SealStamp char="异" size={40} />
          </span>
          <h1>隐私政策</h1>
        </div>
        <div style={{ lineHeight: 1.9, fontSize: 14, textAlign: "left" }}>
          <p><strong>1. 我们收集什么。</strong>注册时收集名号与口令（口令仅以 bcrypt 单向哈希存储）；可选绑定邮箱（仅经验证后保存）。使用过程中记录请求数据（路径、状态码、耗时）与 LLM 调用追踪（输入摘要、输出、耗时），用于服务运营与排障。</p>
          <p><strong>2. 我们如何使用。</strong>提供登录态、推演对战、猜词与后台管理；聚合统计不关联个人身份。</p>
          <p><strong>3. 你的权利。</strong>可在"设置"页随时导出个人数据（JSON）；可自助注销账号——注销后名号与邮箱即被匿名化且不可恢复，刷新令牌全部吊销。</p>
          <p><strong>4. 保留期限。</strong>请求日志默认保留 30 天、LLM 调用追踪默认保留 90 天，到期自动清理。</p>
          <p><strong>5. 第三方。</strong>你的推演输入会发送给为平台提供大模型服务的供应商以完成生成；除此之外不向第三方出售数据。</p>
          <p className="muted">本政策为模板文本，正式运营前请经法务审阅替换。</p>
        </div>
        <p className="auth__foot">
          <Link to="/">返回首页</Link>
          <span className="muted">　·　</span>
          <Link to="/terms">用户协议</Link>
        </p>
      </div>
    </div>
  );
}
