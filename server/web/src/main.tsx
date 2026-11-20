import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createQueryClient } from "./api/queryClient";
import { App } from "./App";
import { Providers } from "./app/Providers";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element");

createRoot(root).render(
  <StrictMode>
    <Providers queryClient={createQueryClient()}>
      <App />
    </Providers>
  </StrictMode>,
);
