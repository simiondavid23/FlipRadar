import { redirect } from "next/navigation";

// FlipRadar — ruta veche pastrata pentru bookmark-uri; redirect catre pagina noua.
export default function AutoListingsSavedPage() {
  redirect("/dashboard/auto-listings/saved");
}
