import * as Tabs from "@radix-ui/react-tabs";
import PageShell from "../components/PageShell";
import ModelProfiles from "../components/ModelProfiles";
import EmailBinding from "../components/EmailBinding";
import DangerZone from "../components/DangerZone";

export default function Settings() {
  return <PageShell title="设置" subtitle="你的偏好与模型配置" back={{to:"/home",label:"返回首页"}}>
    <Tabs.Root defaultValue="models" className="settings-workspace">
      <Tabs.List className="ds-tabs" aria-label="设置分类"><Tabs.Trigger value="models">模型方案</Tabs.Trigger><Tabs.Trigger value="email">邮箱与验证</Tabs.Trigger><Tabs.Trigger value="data">数据与账号</Tabs.Trigger></Tabs.List>
      <Tabs.Content value="models"><ModelProfiles /></Tabs.Content>
      <Tabs.Content value="email"><EmailBinding /></Tabs.Content>
      <Tabs.Content value="data"><DangerZone /></Tabs.Content>
    </Tabs.Root>
  </PageShell>;
}
