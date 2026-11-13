import * as Tabs from "@radix-ui/react-tabs";
import PageShell from "../components/PageShell";
import ModelProfiles from "../components/ModelProfiles";
import EmailBinding from "../components/EmailBinding";
import DangerZone from "../components/DangerZone";

export default function Settings() {
  return <PageShell title="设置" subtitle="管理模型、邮箱与个人数据。" back={{to:"/home",label:"返回书院"}}>
    <Tabs.Root defaultValue="models" className="settings-workspace">
      <Tabs.List className="ds-tabs" aria-label="设置分类"><Tabs.Trigger value="models">模型方案</Tabs.Trigger><Tabs.Trigger value="email">邮箱与验证</Tabs.Trigger><Tabs.Trigger value="data">数据与账号</Tabs.Trigger></Tabs.List>
      <Tabs.Content value="models"><div className="settings-intro"><h2>为你的奇思选择模型</h2><p>添加自己的模型方案，供支持自选模型的环节使用。</p></div><ModelProfiles /></Tabs.Content>
      <Tabs.Content value="email"><div className="settings-intro"><h2>保持联系</h2><p>绑定邮箱，用于验证与密码找回。</p></div><EmailBinding /></Tabs.Content>
      <Tabs.Content value="data"><DangerZone /></Tabs.Content>
    </Tabs.Root>
  </PageShell>;
}
