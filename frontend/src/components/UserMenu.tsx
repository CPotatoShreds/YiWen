import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { GearIcon, LogoutIcon, ShieldIcon, UserRoundIcon } from "./icons";

export default function UserMenu() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return <DropdownMenu.Root>
    <DropdownMenu.Trigger className="user-menu__trigger account-trigger" aria-label="打开账号菜单">
      <span className="account-avatar">{user.username.slice(0, 1)}</span>
      <span className="user-menu__name">{user.username}</span><span aria-hidden="true">⌄</span>
    </DropdownMenu.Trigger>
    <DropdownMenu.Portal><DropdownMenu.Content className="ds-menu" align="end" sideOffset={10}>
      <DropdownMenu.Label className="ds-menu-label"><strong>{user.username}</strong><span>{user.email || "未绑定邮箱"}</span></DropdownMenu.Label>
      <DropdownMenu.Item asChild><Link to="/me"><UserRoundIcon size={16} />用户信息</Link></DropdownMenu.Item>
      <DropdownMenu.Item asChild><Link to="/settings"><GearIcon size={16} />设置</Link></DropdownMenu.Item>
      {user.is_admin && <DropdownMenu.Item asChild><Link to="/admin"><ShieldIcon size={16} />管理</Link></DropdownMenu.Item>}
      <DropdownMenu.Separator className="ds-menu-separator" />
      <DropdownMenu.Item onSelect={() => void logout()}><LogoutIcon size={16} />退出登录</DropdownMenu.Item>
    </DropdownMenu.Content></DropdownMenu.Portal>
  </DropdownMenu.Root>;
}
