import { useState } from "react";

import Splash from "./components/Splash.jsx";
import "./App.css";

export default function App() {
  const [data, setData] = useState(null);

  if (!data) {
    return <Splash onDone={setData} />;
  }

  // Placeholder home: proves the splash loaded real data. The sphere replaces this next.
  return (
    <main className="home">
      <h1 className="home-mark">
        Synd<em>icate</em>
      </h1>
      <p className="home-line">
        {data.destinations.length} destinations · {data.hotels.length} hotels · {data.personas.length} travellers
      </p>
      <p className="home-sub">
        Backend connected · model: {data.health.llm_provider}
      </p>
    </main>
  );
}