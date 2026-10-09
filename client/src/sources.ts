/** Display names and one-line descriptions for download sources. */
export const sources: Record<string, { name: string; description: string }> = {
  soulseek: {
    name: "Soulseek",
    description: "Peer-to-peer; the only source of lossless files.",
  },
  freemp3cloud: { name: "FreeMp3Cloud", description: "MP3 downloads." },
  zvu4no: { name: "zvu4no", description: "MP3 downloads." },
  jiosaavn: {
    name: "JioSaavn",
    description: "AAC 256 kbps; used only as the last-resort fallback.",
  },
};

export const sourceIds = Object.keys(sources);

export const sourceName = (id: string) => sources[id]?.name ?? id;
