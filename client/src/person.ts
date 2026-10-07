import { createContext, useContext } from "react";

/** Whether the signed-in person is the owner, for Admin-only menu items. */
export const OwnerContext = createContext(false);
export const useOwner = () => useContext(OwnerContext);
