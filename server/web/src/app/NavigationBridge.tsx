import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";
import { registerNavigation } from "../api/navigation";

/** Gives the query client a way to move the router. Renders nothing. */
export function NavigationBridge() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    registerNavigation({
      navigate: (to, options) => void navigate(to, options),
      location,
    });
    return () => registerNavigation(null);
  }, [navigate, location]);

  return null;
}
