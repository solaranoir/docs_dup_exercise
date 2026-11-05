import type { AnchorHTMLAttributes, MouseEvent } from "react";
import { navigate } from "../router";

type Props = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { to: string };

/**
 * A real <a href> (so open-in-new-tab, copy link and middle-click work) that navigates in-app
 * on a plain left click.
 */
export function Link({ to, onClick, ...rest }: Props) {
  const handle = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      (rest.target && rest.target !== "_self")
    ) {
      return;
    }
    event.preventDefault();
    navigate(to);
  };
  return <a href={to} onClick={handle} {...rest} />;
}
