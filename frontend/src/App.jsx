import { useCallback, useState } from "react";

import Cursor from "./components/Cursor.jsx";
import Hero from "./components/Hero.jsx";
import Splash from "./components/Splash.jsx";
import "./App.css";

export default function App() {
  const [data, setData] = useState(null);

  // Stable function, so the hero is not rebuilt on every render.
  const pickCity = useCallback((city) => {
    console.log("Picked", city.name, "in", city.state); // the next step zooms into the city from here
  }, []);

  return (
    <>
      <Cursor />
      {data ? <Hero states={data.states} onPickCity={pickCity} /> : <Splash onDone={setData} />}
    </>
  );
}