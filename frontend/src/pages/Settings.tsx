import ModelProfiles from "../components/ModelProfiles";
import EmailBinding from "../components/EmailBinding";
import DangerZone from "../components/DangerZone";
import { CloudDivider } from "../components/Ornaments";
import { Link } from "react-router-dom";

export default function Settings() {
  return (
    <>
      <div className="section-head">
        <div>
          <h1 className="section-title">设置</h1>
          <p className="muted">你的偏好与模型配置</p>
        </div>
        <div className="section-head__exit">
          <Link className="muted" to="/home">返回首页</Link>
        </div>
      </div>
      <CloudDivider />
      <EmailBinding />
      <ModelProfiles />
      <CloudDivider />
      <DangerZone />
    </>
  );
}
