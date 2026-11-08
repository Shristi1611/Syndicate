import { useState } from "react";

import Cursor from "./components/Cursor.jsx";
import Hero from "./components/Hero.jsx";
import Splash from "./components/Splash.jsx";
import "./App.css";

export default function App() {
  const [data, setData] = useState(null);

  return (
    <>
      <Cursor />
      {data ? <Hero /> : <Splash onDone={setData} />}
    </>
  );
}