import PageShell from "../components/PageShell";
import ModelProfiles from "../components/ModelProfiles";
import EmailBinding from "../components/EmailBinding";
import DangerZone from "../components/DangerZone";
import { CloudDivider } from "../components/Ornaments";

export default function Settings() {
  return (
    <PageShell title="设置" subtitle="你的偏好与模型配置" back={{ to: "/home", label: "返回首页" }}>
      <EmailBinding />
      <ModelProfiles />
      <CloudDivider />
      <DangerZone />
    </PageShell>
  );
}
