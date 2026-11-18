import { Component, type ReactNode } from "react";

/** Catches a lazily loaded part of the app that failed to download (flaky connection, a stale tab after a deploy) and
 *  shows the given fallback instead of a blank screen. */
export class ChunkBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
