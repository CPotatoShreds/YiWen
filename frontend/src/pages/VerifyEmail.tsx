import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { SealStamp } from "../components/Ornaments";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"verifying" | "ok" | "fail">("verifying");
  const [detail, setDetail] = useState("");

  useEffect(() => {
    if (!token) {
      setState("fail");
      setDetail("链接缺少验证凭据");
      return;
    }
    api<{ email: string }>("/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) })
      .then((res) => {
        setState("ok");
        setDetail(res.email);
      })
      .catch((e: any) => {
        setState("fail");
        setDetail(e.message);
      });
  }, [token]);

  return (
    <div className="auth">
      <div className="auth__card rise">
        <div className="auth__brand">
          <span className="brand__mark">
            <SealStamp char="异" size={40} />
          </span>
          <h1>邮箱验证</h1>
        </div>
        {state === "verifying" && <p className="auth__sub">验证中…</p>}
        {state === "ok" && <p className="auth__sub">绑定成功：{detail}</p>}
        {state === "fail" && <p className="auth__sub">验证失败：{detail}</p>}
        <p className="auth__foot">
          <Link to="/login">返回登录</Link>
        </p>
      </div>
    </div>
  );
}
